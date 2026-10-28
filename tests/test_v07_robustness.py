from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import database
from app.database import Base
from app.models import Project


def test_recover_interrupted_states_marks_active_projects_failed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

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
