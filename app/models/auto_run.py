from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Passos del mode automàtic, en l'ordre en què s'executen.
AUTO_STEPS = {
    "QUEUED": "En cua",
    "BACKGROUND": "Preparant el fons",
    "AUDIO": "Preparant efectes i música",
    "RENDERING": "Renderitzant el vídeo",
    "PUBLISHING": "Publicant a YouTube",
    "DONE": "Publicat",
    "DONE_LOCAL": "Vídeo fet (sense publicar)",
    "FAILED": "Error",
    "CANCELLED": "Cancel·lat",
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
    # calma, medieval, fosca o jazz; buit = automàtic segons el format i l'entorn.
    music_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Volum de la música (dB respecte del normal): -8, -4, 0 o 3.
    music_level: Mapped[int] = mapped_column(Integer, default=0)
    # Soroll de color: «color» (fons del color del soroll) o «negre»; i si el color «respira».
    noise_screen: Mapped[str | None] = mapped_column(String(10), nullable=True)
    noise_pulse: Mapped[int] = mapped_column(Integer, default=0)
    # Publicar el Short també com a reel a Instagram i a la pàgina de Facebook.
    instagram: Mapped[int] = mapped_column(Integer, default=0)
    facebook: Mapped[int] = mapped_column(Integer, default=0)
    instagram_media_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    facebook_video_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    chime: Mapped[int] = mapped_column(Integer, default=1)
    ambience_level: Mapped[int] = mapped_column(Integer, default=0)
    # Fitxers d'ambient de la mostra escoltada (separats per comes), per a reutilitzar-los.
    ambience_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pomodoro, dormir, llegir, rol o soroll (vegeu FORMATS en autopilot_plan).
    format: Mapped[str] = mapped_column(String(20), default="pomodoro")
    noise: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dim: Mapped[int] = mapped_column(Integer, default=0)
    motion: Mapped[int] = mapped_column(Integer, default=1)
    # En desús: abans demanava generar un fons nou amb Forge. Es conserva per a les bases de dades antigues.
    new_background: Mapped[int] = mapped_column(Integer, default=0)
    # 1 = apagar l'ordinador quan acabe (si és l'últim de la cua i ha anat bé).
    shutdown: Mapped[int] = mapped_column(Integer, default=0)
    # 1 = esborrar video.mp4 uns dies després de publicar-lo (es conserven miniatura i textos).
    delete_after: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Calendari: hora (UTC) a la qual YouTube farà públic el vídeo; reels pendents per a eixa hora.
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reels_due: Mapped[int] = mapped_column(Integer, default=0)
    # Fons triat a mà en el formulari; després de fer el vídeo, el fons que s'ha usat.
    # Respiració guiada: patró (quadrada, 478, coherent).
    breath: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 1 = publicar també un Short vertical que enllaça amb el vídeo.
    shorts: Mapped[int] = mapped_column(Integer, default=0)
    short_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Shorts 2 i 3 (programats per als dies següents), separats per comes.
    extra_short_ids: Mapped[str | None] = mapped_column(String(80), nullable=True)
    background: Mapped[str | None] = mapped_column(String(200), nullable=True)
    step: Mapped[str] = mapped_column(String(20), default="QUEUED")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
