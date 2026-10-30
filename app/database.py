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
        connection.execute(text(
            "UPDATE auto_runs SET step = 'FAILED', error = 'Interromput per un reinici de l''aplicació' "
            "WHERE step IN ('QUEUED', 'BACKGROUND', 'AUDIO', 'RENDERING', 'PUBLISHING')"
        ))
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


# Columnes afegides després de crear la taula; SQLite no les afig amb create_all.
ADDED_COLUMNS = {
    "auto_runs": {
        "music": "INTEGER NOT NULL DEFAULT 0",
        "chime": "INTEGER NOT NULL DEFAULT 1",
        "ambience_level": "INTEGER NOT NULL DEFAULT 0",
        "ambience_files": "TEXT",
        "format": "VARCHAR(20) NOT NULL DEFAULT 'pomodoro'",
        "noise": "VARCHAR(20)",
        "dim": "INTEGER NOT NULL DEFAULT 0",
        "motion": "INTEGER NOT NULL DEFAULT 1",
        "new_background": "INTEGER NOT NULL DEFAULT 0",
        "background": "VARCHAR(200)",
        "shutdown": "INTEGER NOT NULL DEFAULT 0",
        "delete_after": "INTEGER NOT NULL DEFAULT 0",
        "published_at": "DATETIME",
    },
}


def add_missing_columns() -> int:
    added = 0
    with engine.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            existing = {row[1] for row in connection.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            if not existing:
                continue
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added += 1
    return added


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        add_missing_columns()
    recover_interrupted_states()
    cleanup_orphan_outputs()
