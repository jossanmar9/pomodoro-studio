from pathlib import Path
import re
import shutil

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
OUTPUT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-.+-\d{3}(?:-\d+)?$")


def recover_interrupted_states() -> int:
    """Evita deixar projectes eternament en cua o generant després d'un reinici."""
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE projects SET status = 'FAILED' WHERE status IN ('QUEUED', 'GENERATING')")
        )
        return result.rowcount or 0


def cleanup_orphan_outputs(output_dir: Path | None = None) -> int:
    """Elimina només carpetes generades per l'app que ja no referencia cap projecte.

    No toca fitxers arbitraris d'output ni cap carpeta que continue registrada en
    la base de dades. Això recupera resultats antics deixats per reedicions o
    renders substituïts sense arriscar dades externes.
    """
    root = (output_dir or settings.output_dir).resolve()
    if not root.is_dir():
        return 0
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT output_path FROM projects WHERE output_path IS NOT NULL")).fetchall()
    referenced = {Path(row[0]).resolve() for row in rows if row[0]}
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_dir() or not OUTPUT_NAME.fullmatch(candidate.name):
            continue
        resolved = candidate.resolve()
        if resolved.parent != root or resolved in referenced:
            continue
        shutil.rmtree(resolved)
        removed += 1
    return removed


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    recover_interrupted_states()
    cleanup_orphan_outputs()
