from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Preset(Base):
    __tablename__ = "presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    theme: Mapped[str] = mapped_column(String(120))
    focus_minutes: Mapped[int] = mapped_column(Integer, default=25)
    break_minutes: Mapped[int] = mapped_column(Integer, default=5)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=120)
    resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
