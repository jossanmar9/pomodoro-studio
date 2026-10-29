from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Passos del mode automàtic, en l'ordre en què s'executen.
AUTO_STEPS = {
    "QUEUED": "En cua",
    "BACKGROUND": "Creant el fons",
    "AUDIO": "Preparant efectes i música",
    "RENDERING": "Renderitzant el vídeo",
    "PUBLISHING": "Publicant a YouTube",
    "DONE": "Publicat",
    "DONE_LOCAL": "Vídeo fet (sense publicar)",
    "FAILED": "Error",
}
AUTO_ACTIVE_STEPS = {"QUEUED", "BACKGROUND", "AUDIO", "RENDERING", "PUBLISHING"}


class AutoRun(Base):
    __tablename__ = "auto_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    theme: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(40))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    focus_minutes: Mapped[int] = mapped_column(Integer, default=25)
    break_minutes: Mapped[int] = mapped_column(Integer, default=5)
    privacy: Mapped[str] = mapped_column(String(20), default="public")
    publish: Mapped[int] = mapped_column(Integer, default=1)
    music: Mapped[int] = mapped_column(Integer, default=0)
    chime: Mapped[int] = mapped_column(Integer, default=1)
    ambience_level: Mapped[int] = mapped_column(Integer, default=0)
    # Fitxers d'ambient de la mostra escoltada (separats per comes), per a reutilitzar-los.
    ambience_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pomodoro, dormir, rol o soroll (vegeu FORMATS en autopilot_plan).
    format: Mapped[str] = mapped_column(String(20), default="pomodoro")
    noise: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dim: Mapped[int] = mapped_column(Integer, default=0)
    motion: Mapped[int] = mapped_column(Integer, default=1)
    step: Mapped[str] = mapped_column(String(20), default="QUEUED")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
