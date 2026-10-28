from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import database
from app.database import Base
from app.models import Project


def _temporary_engine(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    return engine


def test_recover_interrupted_states_marks_active_projects_failed(tmp_path, monkeypatch):
    engine = _temporary_engine(tmp_path, monkeypatch)
    with Session(engine) as db:
        db.add_all([
            Project(theme="Bosc", status="QUEUED"),
            Project(theme="Bosc", status="GENERATING"),
            Project(theme="Bosc", status="COMPLETED"),
        ])
        db.commit()

    assert database.recover_interrupted_states() == 2

    with Session(engine) as db:
        statuses = [project.status for project in db.query(Project).order_by(Project.id).all()]
    assert statuses == ["FAILED", "FAILED", "COMPLETED"]


def test_cleanup_orphan_outputs_only_removes_generated_unreferenced_dirs(tmp_path, monkeypatch):
    engine = _temporary_engine(tmp_path, monkeypatch)
    output = tmp_path / "output"
    output.mkdir()
    referenced = output / "2026-10-28-bosc-001"
    orphan = output / "2026-10-28-bosc-001-2"
    unrelated = output / "manual-backup"
    for folder in (referenced, orphan, unrelated):
        folder.mkdir()
        (folder / "keep.txt").write_text("x", encoding="utf-8")

    with Session(engine) as db:
        db.add(Project(theme="Bosc", status="COMPLETED", output_path=str(referenced)))
        db.commit()

    assert database.cleanup_orphan_outputs(output) == 1
    assert referenced.is_dir()
    assert not orphan.exists()
    assert unrelated.is_dir()
