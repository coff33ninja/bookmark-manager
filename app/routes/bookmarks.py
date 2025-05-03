from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import Bookmark, BookmarkSchema, SessionLocal, BookmarkCreate
from datetime import datetime
from app.services.metadata_fetcher import fetch_metadata_combined
from pydantic import BaseModel
import json
import logging
from pathlib import Path
from typing import List
import shutil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from collections import defaultdict, Counter

router = APIRouter()

logging.basicConfig(level=logging.INFO, filename="uvicorn.log", filemode="a", format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Predefined tag vocabulary
TAG_VOCAB = [
    "tech", "video", "news", "blog", "social", "education", "entertainment",
    "music", "gaming", "sports", "food", "travel", "health", "finance"
]

# Cache for tag suggestions
TAG_CACHE = {}

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
        icon_candidates = []
        try:
            metadata = fetch_metadata_combined(bookmark.url)
            if "error" not in metadata:
                webicon = metadata.get("webicon", "/static/favicon.ico")
                icon_candidates = metadata.get("icon_candidates", [])
                # Validate icon paths
                icon_candidates = [ic for ic in icon_candidates if (Path("app") / ic.lstrip("/")).exists()]
                for ic in icon_candidates:
                    logger.info(f"Validating icon {ic}: {'valid' if (Path('app') / ic.lstrip('/')).exists() else 'invalid'}")
            else:
                logger.warning(f"Metadata fetch failed for {bookmark.url}: {metadata['error']}")
        except Exception as e:
            logger.error(f"Metadata fetch exception for {bookmark.url}: {str(e)}")
            webicon = "/static/favicon.ico"
            icon_candidates = []

        bookmark_instance = Bookmark(
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            webicon=webicon,
            icon_candidates=",".join(icon_candidates) if icon_candidates else None,
            extra_metadata=(
                json.dumps(bookmark.extra_metadata) if bookmark.extra_metadata else None
            ),
            tags=",".join(bookmark.tags) if bookmark.tags else None,
            is_favorite=bookmark.is_favorite,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_used=None,
            click_count=0,
        )
        db.add(bookmark_instance)
        db.commit()
        db.refresh(bookmark_instance)
        logger.info(f"Bookmark added successfully: ID {bookmark_instance.id}")
        bookmark_instance.tags = bookmark_instance.tags.split(",") if bookmark_instance.tags else []
        bookmark_instance.icon_candidates = (
            bookmark_instance.icon_candidates.split(",") if bookmark_instance.icon_candidates else []
        )
        return bookmark_instance
    except Exception as e:
        logger.error(f"Error adding bookmark: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add bookmark: {str(e)}")

@router.get("/bookmarks", response_model=List[BookmarkSchema])
def get_bookmarks(db: Session = Depends(get_db)):
    try:
        logger.info("Fetching all bookmarks")
        bookmarks = db.query(Bookmark).all()
        logger.info(f"Fetched {len(bookmarks)} bookmarks")
        result = []
        for bookmark in bookmarks:
            try:
                bookmark.tags = (
                    bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
                )
                bookmark.icon_candidates = (
                    bookmark.icon_candidates.split(",")
                    if isinstance(bookmark.icon_candidates, str) and bookmark.icon_candidates
                    else []
                )
                if not bookmark.icon_candidates:
                    try:
                        logger.info(f"Fetching metadata for bookmark {bookmark.id} with URL {bookmark.url}")
                        metadata = fetch_metadata_combined(bookmark.url)
                        if "error" not in metadata:
                            bookmark.icon_candidates = metadata.get("icon_candidates", [bookmark.webicon])
                            bookmark.icon_candidates = bookmark.icon_candidates or [bookmark.webicon]
                            bookmark.icon_candidates = [
                                str(ic) for ic in bookmark.icon_candidates if (Path("app") / str(ic).lstrip("/")).exists()
                            ]
                            bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark.id).first()
                            bookmark_instance.icon_candidates = ",".join(bookmark.icon_candidates) if bookmark.icon_candidates else bookmark.webicon
                            db.commit()
                            logger.info(f"Updated icon_candidates for bookmark {bookmark.id}: {bookmark.icon_candidates}")
                        else:
                            logger.warning(f"Metadata fetch failed for {bookmark.url}: {metadata['error']}")
                            bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for {bookmark.url}: {str(e)}")
                        bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                # Ensure at least one valid icon
                if not bookmark.icon_candidates:
                    logger.info(f"Using fallback icon /static/favicon.ico for {bookmark.url}")
                    bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                result.append(bookmark)
            except Exception as e:
                logger.warning(f"Skipping bookmark {bookmark.id} due to error: {str(e)}")
                continue
        return result
    except Exception as e:
        logger.error(f"Error fetching bookmarks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch bookmarks")

@router.get("/cluster-bookmarks")
def cluster_bookmarks(db: Session = Depends(get_db)):
    try:
        logger.info("Clustering bookmarks")
        bookmarks = db.query(Bookmark).all()
        if len(bookmarks) < 2:
            logger.info("Not enough bookmarks to cluster")
            return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in bookmarks]}]

        # Prepare data for clustering
        texts = []
        valid_bookmarks = []
        for bookmark in bookmarks:
            try:
                # Generate tags for clustering
                tag_response = suggest_tags(TagSuggestionRequest(
                    title=bookmark.title or "",
                    description=bookmark.description or "",
                    url=bookmark.url or ""
                ))
                tags = tag_response["tags"]
                text = " ".join([t for t in tags + [bookmark.title or "", bookmark.description or "", bookmark.url or ""] if t])
                if text.strip():  # Only include non-empty texts
                    texts.append(text.strip())
                    valid_bookmarks.append(bookmark)
                else:
                    logger.warning(f"Skipping bookmark {bookmark.id} due to empty text")
            except Exception as e:
                logger.warning(f"Skipping bookmark {bookmark.id} due to tag suggestion error: {str(e)}")
                continue

        if not texts:
            logger.info("No valid texts for clustering")
            return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in bookmarks]}]

        # TF-IDF vectorization
        try:
            vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
            X = vectorizer.fit_transform(texts)
            logger.info(f"Vectorized {len(texts)} texts with {X.shape[1]} features")
        except Exception as e:
            logger.error(f"TF-IDF vectorization failed: {str(e)}")
            return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in bookmarks]}]

        # Dynamic number of clusters
        n_clusters = min(max(3, len(valid_bookmarks) // 5), 5, len(texts))  # Ensure n_clusters <= n_samples
        try:
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            labels = [int(label) for label in kmeans.fit_predict(X)]  # Convert numpy.int32 to Python int
            logger.info(f"Clustering with labels: {labels}")
        except Exception as e:
            logger.error(f"K-Means clustering failed: {str(e)}")
            return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in bookmarks]}]

        # Group bookmarks by cluster
        clusters = defaultdict(list)
        for idx, (bookmark, label) in enumerate(zip(valid_bookmarks, labels)):
            try:
                extra_metadata = (
                    json.loads(bookmark.extra_metadata) if bookmark.extra_metadata else {}
                )
                bookmark_dict = {
                    "id": int(bookmark.id),
                    "url": bookmark.url or "",
                    "title": bookmark.title or "",
                    "description": bookmark.description or "",
                    "webicon": bookmark.webicon or "/static/favicon.ico",
                    "icon_candidates": (
                        bookmark.icon_candidates.split(",")
                        if isinstance(bookmark.icon_candidates, str) and bookmark.icon_candidates
                        else [bookmark.webicon or "/static/favicon.ico"]
                    ),
                    "extra_metadata": extra_metadata,
                    "tags": (
                        bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
                    ),
                    "is_favorite": bool(bookmark.is_favorite),
                    "created_at": bookmark.created_at.isoformat() if bookmark.created_at else None,
                    "updated_at": bookmark.updated_at.isoformat() if bookmark.updated_at else None,
                    "last_used": bookmark.last_used.isoformat() if bookmark.last_used else None,
                    "click_count": int(bookmark.click_count or 0)
                }
                logger.info(f"Appending bookmark_dict: {bookmark_dict}")
                clusters[label].append(bookmark_dict)
            except Exception as e:
                logger.warning(f"Skipping bookmark {bookmark.id} due to serialization error: {str(e)}")
                continue

        # Label clusters based on most common tags
        result = []
        for cluster_id, bookmarks in clusters.items():
            try:
                all_tags = []
                for bookmark in bookmarks:
                    all_tags.extend(bookmark["tags"])
                tag_counts = Counter(all_tags).most_common(2)
                label = ", ".join(tag for tag, _ in tag_counts) or f"Cluster {cluster_id}"
                cluster_data = {
                    "cluster_id": int(cluster_id),  # Ensure Python int
                    "label": label,
                    "bookmarks": bookmarks
                }
                logger.info(f"Serializing cluster {cluster_id}")
                result.append(cluster_data)
            except Exception as e:
                logger.error(f"Error serializing cluster {cluster_id}: {str(e)}")
                continue

        if not result:
            logger.warning("No valid clusters formed, falling back to All Bookmarks")
            return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in bookmarks]}]

        logger.info(f"Clustered {len(valid_bookmarks)} bookmarks into {len(result)} clusters")
        return result
    except Exception as e:
        logger.error(f"Error clustering bookmarks: {str(e)}", exc_info=True)
        return [{"cluster_id": 0, "label": "All Bookmarks", "bookmarks": [b.__dict__ for b in db.query(Bookmark).all()]}]

@router.patch("/bookmarks/{bookmark_id}", response_model=BookmarkSchema)
def update_bookmark(bookmark_id: int, data: dict, db: Session = Depends(get_db)):
    try:
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
        if "url" in data:
            bookmark_instance.url = data["url"]
        bookmark_instance.updated_at = datetime.now()

        db.commit()
        db.refresh(bookmark_instance)
        bookmark_instance.tags = (
            bookmark_instance.tags.split(",") if isinstance(bookmark_instance.tags, str) and bookmark_instance.tags else []
        )
        bookmark_instance.icon_candidates = (
            bookmark_instance.icon_candidates.split(",")
            if isinstance(bookmark_instance.icon_candidates, str) and bookmark_instance.icon_candidates
            else []
        )
        if not bookmark_instance.icon_candidates:
            try:
                metadata = fetch_metadata_combined(bookmark_instance.url)
                if "error" not in metadata:
                    bookmark_instance.icon_candidates = metadata.get("icon_candidates", [bookmark_instance.webicon])
                    bookmark_instance.icon_candidates = bookmark_instance.icon_candidates or [bookmark_instance.webicon]
                    bookmark_instance.icon_candidates = [
                        str(ic) for ic in bookmark_instance.icon_candidates if (Path("app") / str(ic).lstrip("/")).exists()
                    ]
                    bookmark_instance.icon_candidates = ",".join(bookmark_instance.icon_candidates) if bookmark_instance.icon_candidates else bookmark_instance.webicon
                    db.commit()
                    logger.info(f"Updated icon_candidates for bookmark {bookmark_id}: {bookmark_instance.icon_candidates}")
                else:
                    logger.warning(f"Metadata fetch failed for {bookmark_instance.url}: {metadata['error']}")
                    bookmark_instance.icon_candidates = [bookmark_instance.webicon or "/static/favicon.ico"]
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for {bookmark_instance.url}: {str(e)}")
                bookmark_instance.icon_candidates = [bookmark_instance.webicon or "/static/favicon.ico"]
        logger.info(f"Updated bookmark {bookmark_id}")
        return bookmark_instance
    except Exception as e:
        logger.error(f"Error updating bookmark {bookmark_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update bookmark: {str(e)}")

@router.patch("/bookmarks/{bookmark_id}/webicon", response_model=BookmarkSchema)
def update_bookmark_webicon(bookmark_id: int, data: dict, db: Session = Depends(get_db)):
    try:
        bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark_id).first()
        if not bookmark_instance:
            logger.error(f"Bookmark {bookmark_id} not found")
            raise HTTPException(status_code=404, detail="Bookmark not found")

        new_webicon = data.get("webicon")
        if not new_webicon:
            logger.error("No webicon provided")
            raise HTTPException(status_code=400, detail="Webicon path required")

        icon_path = Path("app") / new_webicon.lstrip("/")
        if not icon_path.exists() or not icon_path.is_file():
            logger.error(f"Invalid webicon path: {new_webicon}")
            raise HTTPException(status_code=400, detail="Invalid webicon path")

        from urllib.parse import urlparse
        domain = urlparse(bookmark_instance.url).netloc.replace(".", "_")
        expected_dir = Path("app/static/icons") / domain
        if not icon_path.parent == expected_dir:
            logger.error(f"Webicon {new_webicon} not in domain folder {expected_dir}")
            raise HTTPException(status_code=400, detail="Webicon must be in domain's icon folder")

        bookmark_instance.webicon = new_webicon
        bookmark_instance.updated_at = datetime.now()
        db.commit()
        db.refresh(bookmark_instance)
        bookmark_instance.tags = (
            bookmark_instance.tags.split(",") if isinstance(bookmark_instance.tags, str) and bookmark_instance.tags else []
        )
        bookmark_instance.icon_candidates = (
            bookmark_instance.icon_candidates.split(",")
            if isinstance(bookmark_instance.icon_candidates, str) and bookmark_instance.icon_candidates
            else []
        )
        if not bookmark_instance.icon_candidates:
            try:
                metadata = fetch_metadata_combined(bookmark_instance.url)
                if "error" not in metadata:
                    bookmark_instance.icon_candidates = metadata.get("icon_candidates", [bookmark_instance.webicon])
                    bookmark_instance.icon_candidates = bookmark_instance.icon_candidates or [bookmark_instance.webicon]
                    bookmark_instance.icon_candidates = [
                        str(ic) for ic in bookmark_instance.icon_candidates if (Path("app") / str(ic).lstrip("/")).exists()
                    ]
                    bookmark_instance.icon_candidates = ",".join(bookmark_instance.icon_candidates) if bookmark_instance.icon_candidates else bookmark_instance.webicon
                    db.commit()
                    logger.info(f"Updated icon_candidates for bookmark {bookmark_id}: {bookmark_instance.icon_candidates}")
                else:
                    logger.warning(f"Metadata fetch failed for {bookmark_instance.url}: {metadata['error']}")
                    bookmark_instance.icon_candidates = [bookmark_instance.webicon or "/static/favicon.ico"]
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for {bookmark_instance.url}: {str(e)}")
                bookmark_instance.icon_candidates = [bookmark_instance.webicon or "/static/favicon.ico"]
        logger.info(f"Updated webicon for bookmark {bookmark_id} to {new_webicon}")
        return bookmark_instance
    except Exception as e:
        logger.error(f"Error updating webicon for bookmark {bookmark_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update webicon: {str(e)}")

@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int, db: Session = Depends(get_db)):
    try:
        bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark_id).first()
        if not bookmark_instance:
            logger.error(f"Bookmark {bookmark_id} not found")
            raise HTTPException(status_code=404, detail="Bookmark not found")

        # Move icons to recycled_icons
        from urllib.parse import urlparse
        domain = urlparse(bookmark_instance.url).netloc.replace(".", "_")
        recycle_dir = Path("app/static/recycled_icons") / domain
        recycle_dir.mkdir(parents=True, exist_ok=True)

        icons_to_move = []
        if bookmark_instance.webicon and bookmark_instance.webicon != "/static/favicon.ico":
            icons_to_move.append(bookmark_instance.webicon)
        if bookmark_instance.icon_candidates:
            icon_candidates = (
                bookmark_instance.icon_candidates.split(",")
                if isinstance(bookmark_instance.icon_candidates, str)
                else []
            )
            icons_to_move.extend([ic for ic in icon_candidates if ic != "/static/favicon.ico"])

        for icon_path in set(icons_to_move):
            try:
                src_path = Path("app") / icon_path.lstrip("/")
                if src_path.exists() and src_path.is_file():
                    dest_path = recycle_dir / src_path.name
                    shutil.move(str(src_path), str(dest_path))
                    logger.info(f"Moved icon {src_path} to {dest_path}")
                else:
                    logger.warning(f"Icon {src_path} does not exist or is not a file")
            except Exception as e:
                logger.warning(f"Failed to move icon {icon_path}: {str(e)}")

        db.delete(bookmark_instance)
        db.commit()
        logger.info(f"Deleted bookmark {bookmark_id}")
        return {"message": "Bookmark deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting bookmark {bookmark_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete bookmark: {str(e)}")

class MetadataRequest(BaseModel):
    url: str

@router.post("/fetch-metadata")
def get_metadata(request: MetadataRequest, db: Session = Depends(get_db)):
    try:
        logger.info(f"Fetching metadata for URL: {request.url}")
        existing_bookmark = db.query(Bookmark).filter(Bookmark.url == request.url).first()
        if existing_bookmark and existing_bookmark.webicon:
            icon_path = Path("app") / existing_bookmark.webicon.lstrip("/")
            if icon_path.exists() and icon_path.stat().st_size > 0:
                logger.info(f"Reusing existing favicon for {request.url}: {existing_bookmark.webicon}")
                metadata = fetch_metadata_combined(request.url)
                if "error" in metadata:
                    logger.warning(f"Metadata fetch failed for {request.url}: {metadata['error']}")
                    return {
                        "title": existing_bookmark.title or "No title",
                        "description": existing_bookmark.description or "",
                        "webicon": existing_bookmark.webicon,
                        "icon_candidates": [existing_bookmark.webicon],
                        "extra_metadata": {}
                    }
                icon_candidates = metadata.get("icon_candidates", [existing_bookmark.webicon])
                icon_candidates = [ic for ic in icon_candidates if (Path("app") / ic.lstrip("/")).exists()]
                for ic in icon_candidates:
                    logger.info(f"Validating icon {ic}: {'valid' if (Path('app') / ic.lstrip('/')).exists() else 'invalid'}")
                return {
                    "title": existing_bookmark.title,
                    "description": existing_bookmark.description,
                    "webicon": existing_bookmark.webicon,
                    "icon_candidates": icon_candidates or [existing_bookmark.webicon],
                    "extra_metadata": metadata.get("extra_metadata", {})
                }

        metadata = fetch_metadata_combined(request.url)
        if "error" in metadata:
            logger.error(f"Failed to fetch metadata for {request.url}: {metadata['error']}")
            return {
                "title": "No title",
                "description": "",
                "webicon": "/static/favicon.ico",
                "icon_candidates": ["/static/favicon.ico"],
                "extra_metadata": {}
            }
        icon_candidates = metadata.get("icon_candidates", [metadata.get("webicon", "/static/favicon.ico")])
        icon_candidates = [ic for ic in icon_candidates if (Path("app") / ic.lstrip("/")).exists()]
        for ic in icon_candidates:
            logger.info(f"Validating icon {ic}: {'valid' if (Path('app') / ic.lstrip('/')).exists() else 'invalid'}")
        if not icon_candidates:
            logger.info(f"Using fallback icon /static/favicon.ico for {request.url}")
            icon_candidates = [metadata.get("webicon", "/static/favicon.ico")]
        logger.info(f"Metadata fetched successfully for {request.url}: webicon={metadata.get('webicon')}, candidates={icon_candidates}")
        return {
            "title": metadata.get("title", "No title"),
            "description": metadata.get("description", ""),
            "webicon": metadata.get("webicon", "/static/favicon.ico"),
            "icon_candidates": icon_candidates,
            "extra_metadata": metadata.get("extra_metadata", {})
        }
    except Exception as e:
        logger.error(f"Error in fetch-metadata for {request.url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {str(e)}")

@router.get("/search", response_model=List[BookmarkSchema])
def search_bookmarks(query: str, db: Session = Depends(get_db)):
    try:
        logger.info(f"Searching bookmarks with query: {query}")
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
        result = []
        for bookmark in bookmarks:
            try:
                bookmark.tags = (
                    bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
                )
                bookmark.icon_candidates = (
                    bookmark.icon_candidates.split(",")
                    if isinstance(bookmark.icon_candidates, str) and bookmark.icon_candidates
                    else []
                )
                if not bookmark.icon_candidates:
                    try:
                        metadata = fetch_metadata_combined(bookmark.url)
                        if "error" not in metadata:
                            bookmark.icon_candidates = metadata.get("icon_candidates", [bookmark.webicon])
                            bookmark.icon_candidates = bookmark.icon_candidates or [bookmark.webicon]
                            bookmark.icon_candidates = [
                                str(ic) for ic in bookmark.icon_candidates if (Path("app") / str(ic).lstrip("/")).exists()
                            ]
                            bookmark_instance = db.query(Bookmark).filter(Bookmark.id == bookmark.id).first()
                            bookmark_instance.icon_candidates = ",".join(bookmark.icon_candidates) if bookmark.icon_candidates else bookmark.webicon
                            db.commit()
                            logger.info(f"Updated icon_candidates воздух bookmark {bookmark.id}: {bookmark.icon_candidates}")
                        else:
                            logger.warning(f"Metadata fetch failed for {bookmark.url}: {metadata['error']}")
                            bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for {bookmark.url}: {str(e)}")
                        bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                # Ensure at least one valid icon
                if not bookmark.icon_candidates:
                    logger.info(f"Using fallback icon /static/favicon.ico for {bookmark.url}")
                    bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                result.append(bookmark)
            except Exception as e:
                logger.warning(f"Skipping bookmark {bookmark.id} due to error: {str(e)}")
                continue
        return result
    except Exception as e:
        logger.error(f"Error searching bookmarks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to search bookmarks: {str(e)}")

class TagSuggestionRequest(BaseModel):
    title: str
    description: str = ""
    url: str

@router.post("/suggest-tags")
def suggest_tags(request: TagSuggestionRequest):
    try:
        # Check cache
        cache_key = f"{request.title}:{request.description}:{request.url}"
        if cache_key in TAG_CACHE:
            logger.info(f"Returning cached tags for {cache_key[:50]}...")
            return {"tags": TAG_CACHE[cache_key]}

        # Combine inputs for vectorization
        text = f"{request.title} {request.description} {request.url}"
        logger.info(f"Suggesting tags for text: {text[:100]}...")

        # TF-IDF vectorization and cosine similarity
        vectorizer = TfidfVectorizer(stop_words="english")
        X = vectorizer.fit_transform([text] + TAG_VOCAB)
        similarities = cosine_similarity(X[0:1], X[1:])[0]
        logger.info(f"Similarity scores: {dict(zip(TAG_VOCAB, similarities))}")
        suggested_tags = [
            TAG_VOCAB[i] for i, sim in sorted(enumerate(similarities), key=lambda x: x[1], reverse=True)
            if sim > 0.1
        ][:3]

        # Cache result
        TAG_CACHE[cache_key] = suggested_tags
        if len(TAG_CACHE) > 1000:  # Limit cache size
            TAG_CACHE.pop(next(iter(TAG_CACHE)))

        logger.info(f"Suggested tags: {suggested_tags}")
        return {"tags": suggested_tags}
    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}", exc_info=True)
        return {"tags": [], "message": f"Failed to suggest tags: {str(e)}"}