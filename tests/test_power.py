import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import AutoRun
from app.services import autopilot as auto
from app.services import power as power_module
from app.services.power import PowerManager


@pytest.fixture
def calls(monkeypatch):
    executed = []
    monkeypatch.setattr(power_module, "run_shutdown_command", executed.append)
    return executed


def test_shutdown_waits_and_can_be_cancelled(calls):
    manager = PowerManager()
    manager.schedule("prova", delay=0.2)
    status = manager.status()
    assert status["scheduled"] and status["reason"] == "prova" and status["seconds_left"] <= 1
    assert manager.cancel() is True
    time.sleep(0.4)
    assert calls == [] and manager.status()["scheduled"] is False
    assert manager.cancel() is False

    manager.schedule("ara sí", delay=0.1)
    time.sleep(0.4)
    assert calls == ["systemctl poweroff"]
    assert manager.status() == {"scheduled": False, "error": None}


def test_failed_shutdown_is_reported(monkeypatch):
    def fail(command):
        raise PermissionError("no autoritzat")
    monkeypatch.setattr(power_module, "run_shutdown_command", fail)
    manager = PowerManager()
    manager.schedule("prova", delay=0.05)
    time.sleep(0.3)
    assert "No s'ha pogut apagar" in manager.status()["error"]


@pytest.mark.parametrize("step,publish,shutdown,expected", [
    ("DONE", 1, 1, True),
    ("DONE_LOCAL", 0, 1, True),     # no s'havia de publicar: ha acabat bé
    ("DONE_LOCAL", 1, 1, False),    # YouTube no connectat: millor que ho veges
    ("FAILED", 1, 1, False),
    ("DONE", 1, 0, False),
])
def test_only_successful_runs_shut_down(step, publish, shutdown, expected):
    run = SimpleNamespace(step=step, publish=publish, shutdown=shutdown)
    assert auto.should_shut_down(run) is expected


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    for module in (auto, main):
        monkeypatch.setattr(module, "SessionLocal", session)
    return session


def test_runner_shuts_down_only_after_the_last_video(db, monkeypatch):
    scheduled = []
    monkeypatch.setattr(auto.power, "schedule", lambda reason, delay=None: scheduled.append(reason))
    monkeypatch.setattr(auto.power, "cancel", lambda: False)
    with db() as session:
        session.add_all([
            AutoRun(id=1, theme="Bosc", environment="bosc", duration_minutes=60, shutdown=1),
            AutoRun(id=2, theme="Bosc", environment="bosc", duration_minutes=60, shutdown=1),
        ])
        session.commit()

    def fake_execute(run_id):
        with db() as session:
            session.get(AutoRun, run_id).step = "DONE"
            session.commit()

    monkeypatch.setattr(auto, "execute", fake_execute)
    runner = auto.AutopilotRunner()
    runner._queue = [("run", 1), ("run", 2)]
    runner._loop()
    assert scheduled == ["Vídeo #2 · Bosc acabat"]


def test_new_work_cancels_a_pending_shutdown(monkeypatch, calls):
    manager = PowerManager()
    monkeypatch.setattr(auto, "power", manager)
    monkeypatch.setattr(auto, "execute", lambda run_id: None)
    monkeypatch.setattr(auto, "maybe_schedule_shutdown", lambda run_id: False)
    manager.schedule("prova", delay=5)
    auto.AutopilotRunner().submit(99)
    assert manager.status()["scheduled"] is False


def test_status_and_cancel_endpoints(db, monkeypatch, calls):
    manager = PowerManager()
    monkeypatch.setattr(main, "power", manager)
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert "Apagar l'ordinador en acabar" in client.get("/").text
        manager.schedule("Vídeo #1 · Bosc acabat", delay=60)
        status = client.get("/api/auto").json()["shutdown"]
        assert status["scheduled"] and 55 <= status["seconds_left"] <= 60
        assert client.post("/api/shutdown/cancel").json() == {"cancelled": True}
        assert client.get("/api/auto").json()["shutdown"]["scheduled"] is False
        client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "shutdown": "1"}, follow_redirects=False)
    with db() as session:
        assert session.query(AutoRun).one().shutdown == 1
    assert calls == []
