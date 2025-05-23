from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Text,
    create_engine,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

Base = declarative_base()


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    webicon = Column(String, nullable=True)
    icon_candidates = Column(Text, nullable=True)  # Comma-separated list
    extra_metadata = Column(Text, nullable=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tags = Column(Text, nullable=True)  # Comma-separated list
    is_favorite = Column(Boolean, default=False)
    click_count = Column(Integer, default=0)
    full_text_content = Column(Text, nullable=True)
    content_fetched_at = Column(DateTime, nullable=True)

    __table_args__ = (  # type: ignore
        Index("ix_bookmark_title", "title"),
        Index("ix_bookmark_description", "description"),
        Index("ix_bookmark_url", "url"),
    )


class BookmarkSchema(BaseModel):
    id: int
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    webicon: Optional[str] = None
    icon_candidates: Optional[List[str]] = []
    extra_metadata: Optional[dict] = None
    last_used: Optional[datetime] = None
    created_at: datetime = datetime.utcnow()
    updated_at: Optional[datetime] = datetime.utcnow()
    # updated_at: Optional[datetime] = None

    tags: Optional[List[str]] = None
    is_favorite: bool = False
    click_count: int = 0
    full_text_content: Optional[str] = None
    content_fetched_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BookmarkCreate(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    webicon: Optional[str] = None
    extra_metadata: Optional[dict] = None
    tags: Optional[List[str]] = None
    is_favorite: bool = False


# SQLite database setup
DATABASE_URL = "sqlite:///./bookmarks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)
