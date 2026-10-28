from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class YouTubePublication(Base):
    __tablename__ = "youtube_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    privacy: Mapped[str] = mapped_column(String(20), default="private")
    category_id: Mapped[str] = mapped_column(String(20), default="27")
    status: Mapped[str] = mapped_column(String(30), default="NOT_PUBLISHED")
    video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
