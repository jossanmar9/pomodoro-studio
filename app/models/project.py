from datetime import datetime
from enum import Enum
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class ProjectStatus(str, Enum):
    DRAFT="DRAFT"; QUEUED="QUEUED"; GENERATING="GENERATING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELLED="CANCELLED"

class Project(Base):
    __tablename__="projects"
    id:Mapped[int]=mapped_column(primary_key=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    theme:Mapped[str]=mapped_column(String(120))
    focus_minutes:Mapped[int]=mapped_column(Integer,default=25)
    break_minutes:Mapped[int]=mapped_column(Integer,default=5)
    duration_minutes:Mapped[int]=mapped_column(Integer,default=120)
    resolution:Mapped[str]=mapped_column(String(20),default="1920x1080")
    status:Mapped[str]=mapped_column(String(20),default=ProjectStatus.DRAFT.value)
    output_path:Mapped[str|None]=mapped_column(String(500),nullable=True)
