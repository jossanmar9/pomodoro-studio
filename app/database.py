from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


if settings.database_url.startswith("sqlite"):
    Path("data").mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def recover_interrupted_states() -> int:
    """Evita deixar projectes eternament en cua o generant després d'un reinici."""
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE projects SET status = 'FAILED' WHERE status IN ('QUEUED', 'GENERATING')")
        )
        return result.rowcount or 0


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    recover_interrupted_states()
