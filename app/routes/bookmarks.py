from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import Bookmark, BookmarkSchema, SessionLocal, BookmarkCreate
from datetime import datetime
from app.services.metadata_fetcher import fetch_metadata_combined
from pydantic import BaseModel
import json
import logging
from pathlib import Path

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/bookmarks", response_model=BookmarkSchema)
def add_bookmark(bookmark: BookmarkCreate, db: Session = Depends(get_db)):
    try:
        logger.info(f"Adding bookmark: {bookmark.dict()}")
        webicon = bookmark.webicon or "/static/favicon.ico"
        if webicon.startswith(("http://", "https://")):
            metadata = fetch_metadata_combined(bookmark.url)
            if "error" not in metadata:
                webicon = metadata.get("webicon", "/static/favicon.ico")
            else:
                logger.warning(
                    f"Metadata fetch failed for {bookmark.url}, using default icon"
                )

        bookmark_instance = Bookmark(
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            webicon=webicon,
            extra_metadata=(
                json.dumps(bookmark.extra_metadata) if bookmark.extra_metadata else None
            ),
            tags=",".join(bookmark.tags) if bookmark.tags else None,
            is_favorite=bookmark.is_favorite,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(bookmark_instance)
        db.commit()
        db.refresh(bookmark_instance)
        return bookmark_instance
    except Exception as e:
        logger.error(f"Error adding bookmark: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookmarks", response_model=list[BookmarkSchema])
def get_bookmarks(db: Session = Depends(get_db)):
    bookmarks = db.query(Bookmark).all()
    logger.info(f"Fetched {len(bookmarks)} bookmarks")
    return bookmarks


@router.patch("/bookmarks/{bookmark_id}", response_model=BookmarkSchema)
def update_bookmark(bookmark_id: int, data: dict, db: Session = Depends(get_db)):
    bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark_id).first()
    if not bookmark_instance:
        logger.error(f"Bookmark {bookmark_id} not found")
        raise HTTPException(status_code=404, detail="Bookmark not found")

    if "title" in data:
        bookmark_instance.title = data["title"]
    if "description" in data:
        bookmark_instance.description = data["description"]
    if "tags" in data:
        bookmark_instance.tags = ",".join(data["tags"]) if data["tags"] else None
    if "is_favorite" in data:
        bookmark_instance.is_favorite = data["is_favorite"]
    if "webicon" in data:
        bookmark_instance.webicon = data["webicon"]
    bookmark_instance.updated_at = datetime.now()

    db.commit()
    db.refresh(bookmark_instance)
    logger.info(f"Updated bookmark {bookmark_id}")
    return bookmark_instance


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int, db: Session = Depends(get_db)):
    bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark_id).first()
    if not bookmark_instance:
        logger.error(f"Bookmark {bookmark_id} not found")
        raise HTTPException(status_code=404, detail="Bookmark not found")

    db.delete(bookmark_instance)
    db.commit()
    logger.info(f"Deleted bookmark {bookmark_id}")
    return {"message": "Bookmark deleted successfully"}


class MetadataRequest(BaseModel):
    url: str


@router.post("/fetch-metadata")
def get_metadata(request: MetadataRequest, db: Session = Depends(get_db)):
    logger.info(f"Fetching metadata for URL: {request.url}")
    existing_bookmark = db.query(Bookmark).filter(Bookmark.url == request.url).first()
    if existing_bookmark and existing_bookmark.webicon:
        icon_path = Path("app") / existing_bookmark.webicon.lstrip("/")
        if icon_path.exists() and icon_path.stat().st_size > 0:
            logger.info(
                f"Reusing existing favicon for {request.url}: {existing_bookmark.webicon}"
            )
            return {
                "title": existing_bookmark.title,
                "description": existing_bookmark.description,
                "webicon": existing_bookmark.webicon,
                "icon_candidates": [existing_bookmark.webicon],
            }

    metadata = fetch_metadata_combined(request.url)
    if "error" in metadata:
        logger.error(f"Failed to fetch metadata for {request.url}: {metadata['error']}")
        return {
            "title": "No title",
            "description": "",
            "webicon": "/static/favicon.ico",
            "icon_candidates": [],
        }

    return metadata


@router.get("/search", response_model=list[BookmarkSchema])
def search_bookmarks(query: str, db: Session = Depends(get_db)):
    bookmarks = (
        db.query(Bookmark)
        .filter(
            (Bookmark.title.ilike(f"%{query}%"))
            | (Bookmark.description.ilike(f"%{query}%"))
            | (Bookmark.url.ilike(f"%{query}%"))
        )
        .all()
    )
    logger.info(f"Search query '{query}' returned {len(bookmarks)} results")
    return bookmarks
