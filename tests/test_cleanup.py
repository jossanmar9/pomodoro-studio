from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AutoRun, Project
from app.services import autopilot as auto


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(auto, "SessionLocal", factory)
    monkeypatch.setattr(auto.settings, "keep_published_days", 3)
    return factory


def make(session, tmp_path, n, *, days_ago, delete_after=1, step="DONE"):
    folder = tmp_path / f"video-{n}"
    folder.mkdir()
    for name in ("video.mp4", "thumbnail.jpg", "description.txt", "publication-package.zip"):
        (folder / name).write_bytes(b"x")
    with session() as db:
        project = Project(theme="Bosc", output_path=str(folder), status="COMPLETED")
        db.add(project)
        db.commit()
        run = AutoRun(theme="Bosc", environment="bosc", duration_minutes=60, project_id=project.id, step=step,
                      video_id=f"vid{n}", delete_after=delete_after, published_at=datetime.utcnow() - timedelta(days=days_ago))
        db.add(run)
        db.commit()
        return run.id, folder


def test_only_old_published_videos_marked_for_deletion_are_removed(session, tmp_path):
    old, old_folder = make(session, tmp_path, 1, days_ago=4)
    recent, recent_folder = make(session, tmp_path, 2, days_ago=1)
    kept, kept_folder = make(session, tmp_path, 3, days_ago=10, delete_after=0)
    failed, failed_folder = make(session, tmp_path, 4, days_ago=10, step="FAILED")

    assert auto.cleanup_published_videos() == 1
    assert not (old_folder / "video.mp4").exists() and not (old_folder / "publication-package.zip").exists()
    assert (old_folder / "thumbnail.jpg").exists() and (old_folder / "description.txt").exists()
    for folder in (recent_folder, kept_folder, failed_folder):
        assert (folder / "video.mp4").exists()
    assert auto.cleanup_published_videos() == 0  # no torna a fer res

    with session() as db:
        summary = auto.run_summary(db.get(AutoRun, old))
        assert summary["video_available"] is False and "esborrat" in summary["message"]
        recent_summary = auto.run_summary(db.get(AutoRun, recent))
        assert recent_summary["video_available"] is True
        assert recent_summary["delete_on"] == (datetime.utcnow() + timedelta(days=2)).date().isoformat()
        assert auto.run_summary(db.get(AutoRun, kept))["delete_on"] is None
