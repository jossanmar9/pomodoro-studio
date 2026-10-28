from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RenderConfig(Base):
    __tablename__ = "render_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    engine: Mapped[str] = mapped_column(String(20), default="auto")
    quality: Mapped[str] = mapped_column(String(20), default="balanced")
    actual_engine: Mapped[str | None] = mapped_column(String(20), nullable=True)
