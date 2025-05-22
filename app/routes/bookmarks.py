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
from urllib.parse import urlparse
from app.services.network_detector import NetworkDetector

router = APIRouter()

logging.basicConfig(level=logging.INFO, filename="uvicorn.log", filemode="a", format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Base tag vocabulary
TAG_VOCAB = [
    "tech", "video", "news", "blog", "social", "education", "entertainment",
    "music", "gaming", "sports", "food", "travel", "health", "finance", "anime",
    "manga", "movie", "book", "tv", "podcast", "documentary", "article",
    "tutorial", "recipe", "review", "how-to", "guide", "lifestyle", "fashion",
    "shopping", "portfolio", "forum", "productivity", "science", "art",
    "photography", "coding", "design", "programming", "development", "business",
    "local-server", "remote-server", "vpn-server", "local-server-online",
    "local-server-offline", "remote-server-online", "remote-server-offline",
    "vpn-server-online", "vpn-server-offline", "unknown-server", "invalid-server",
    "AI", "artificial-intelligence", "deep-learning", "natural-language-processing",
    "computer-vision", "machine-learning", "data-science", "data-visualization",
    "assistant", "chatbots", "streaming", "software", "portable", "downloads",
    "networking", "cloud-computing", "cloud-storage", "cloud-services",
    "cloud-hosting", "web-development", "web-design", "web-hosting",
    "web-services", "web-applications", "tools", "productivity-tools",
    "music-generation", "art-generation", "image-generation", "video-generation",
    "text-generation", "3d-modeling", "3d-design", "3d-animation",
    "genshin-impact", "gaming-tools", "e-commerce", "fitness", "writing",
    "collaboration", "open-source", "tutorials", "creative"
]

# User-provided tags for training
USER_TAG_VOCAB = [
    "AI", "anime", "coding", "music", "blog", "games", "video", "social",
    "vpn-server", "manga", "data-science", "machine-learning", "art", "chatbots",
    "development", "genshin-impact", "streaming", "software", "portable",
    "downloads", "networking", "tools", "music-generation", "art-generation",
    "image-generation", "gaming-tools", "open-source", "collaboration"
]

# Define the path to the user tags JSON file
USER_TAGS_FILE = Path("app") / "user_tags.json"

# Load user tags from JSON file if it exists
if USER_TAGS_FILE.exists():
    try:
        with USER_TAGS_FILE.open("r") as f:
            loaded_tags = json.load(f)
        if isinstance(loaded_tags, list) and all(isinstance(tag, str) for tag in loaded_tags):
            USER_TAG_VOCAB = loaded_tags
            logger.info(f"Successfully loaded user tags from {USER_TAGS_FILE}")
        else:
            logger.warning(
                f"Content of {USER_TAGS_FILE} is not a list of strings. "
                "Using default USER_TAG_VOCAB."
            )
    except json.JSONDecodeError:
        logger.warning(
            f"Error decoding JSON from {USER_TAGS_FILE}. "
            "File might be corrupted. Using default USER_TAG_VOCAB."
        )
    except IOError:
        logger.error(
            f"Could not read {USER_TAGS_FILE}. Using default USER_TAG_VOCAB."
        )
else:
    logger.info(
        f"{USER_TAGS_FILE} not found. Using default USER_TAG_VOCAB. "
        "It will be created if new tags are added."
    )


# Domain to type mapping for categorization
DOMAIN_TYPES = {
    "youtube.com": "video",
    "youtu.be": "video",
    "vimeo.com": "video",
    "news": "news",
    "blog": "blog",
    "medium.com": "blog",
    "twitter.com": "social",
    "reddit.com": "social",
    "facebook.com": "social",
    "linkedin.com": "social",
    "wikipedia.org": "education",
    "coursera.org": "education",
    "edx.org": "education",
    "spotify.com": "music",
    "soundcloud.com": "music",
    "twitch.tv": "gaming",
    "espn.com": "sports",
    "allrecipes.com": "food",
    "epicurious.com": "food",
    "tripadvisor.com": "travel",
    "healthline.com": "health",
    "webmd.com": "health",
    "bloomberg.com": "finance",
    "cnbc.com": "finance",
    "crunchyroll.com": "anime",
    "theresanaiforthat.com": "AI",
    "grok.com": "AI",
    "chatgpt.com": "AI",
    "gemini.google.com": "AI",
    "pogs.cafe": "AI",
    "civitai.com": "AI",
    "chat.deepseek.com": "AI",
    "lovable.dev": "AI",
    "hianimez.to": "anime",
    "allmanga.to": "manga",
    "github.com": "coding",
    "kaggle.com": "data-science",
    "colab.research.google.com": "machine-learning",
    "dashboard.ngrok.com": "vpn-server",
    "tailscale.com": "vpn-server",
    "pinggy.io": "vpn-server",
    "riffusion.com": "music-generation",
    "suno.com": "music-generation",
    "fcportables.com": "software",
    "filecr.com": "software",
    "paimon.moe": "gaming-tools",
    "instagram.com": "social",
    "tiktok.com": "social",
    "netflix.com": "streaming",
    "hulu.com": "streaming",
    "amazon.com": "e-commerce",
    "ebay.com": "e-commerce",
    "fitbit.com": "fitness",
    "myfitnesspal.com": "fitness",
    "stackoverflow.com": "coding",
    "dev.to": "coding",
    "huggingface.co": "AI",
    "openai.com": "AI",
    "anilist.co": "anime",
    "mangadex.org": "manga",
    "bandcamp.com": "music",
    "steamcommunity.com": "gaming",
    "patreon.com": "creative",
    "behance.net": "art",
    "dribbble.com": "design",
}

# Cache for tag suggestions
TAG_CACHE = {}
network_detector = NetworkDetector()

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
                icon_candidates = [ic for ic in icon_candidates if (Path("app") / ic.lstrip("/")).exists()]
                for ic in icon_candidates:
                    logger.info(f"Validating icon {ic}: {'valid' if (Path('app') / ic.lstrip('/')).exists() else 'invalid'}")
            else:
                logger.warning(f"Metadata fetch failed for {bookmark.url}: {metadata['error']}")
        except Exception as e:
            logger.error(f"Metadata fetch exception for {bookmark.url}: {str(e)}")
            webicon = "/static/favicon.ico"
            icon_candidates = []

        # Add network tag for IP-based URLs
        tags = bookmark.tags or []
        if network_detector.is_ip_url(bookmark.url):
            network_tag = network_detector.get_network_tag(bookmark.url)
            if network_tag not in tags:
                tags.append(network_tag)

        bookmark_instance = Bookmark(
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            webicon=webicon,
            icon_candidates=",".join(icon_candidates) if icon_candidates else None,
            extra_metadata=(
                json.dumps(bookmark.extra_metadata) if bookmark.extra_metadata else None
            ),
            tags=",".join(tags) if tags else None,
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

@router.get("/categorize-bookmarks")
def categorize_bookmarks(db: Session = Depends(get_db)):
    try:
        logger.info("Categorizing bookmarks")
        bookmarks = db.query(Bookmark).all()
        if not bookmarks:
            logger.info("No bookmarks to categorize")
            return [{"category_id": 0, "label": "Untagged", "bookmarks": []}]

        # Separate untagged, IP-based, and tagged bookmarks
        untagged_bookmarks = []
        ip_bookmarks = []
        tagged_bookmarks = []
        for bookmark in bookmarks:
            tags = bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
            if not tags or all(not t.strip() for t in tags):
                untagged_bookmarks.append(bookmark)
            elif network_detector.is_ip_url(bookmark.url):
                ip_bookmarks.append(bookmark)
            else:
                tagged_bookmarks.append(bookmark)

        result = []

        # Add untagged bookmarks at the top
        if untagged_bookmarks:
            untagged_data = {
                "category_id": -1,
                "label": "Untagged",
                "bookmarks": [
                    {
                        "id": int(b.id),
                        "url": b.url or "",
                        "title": b.title or "",
                        "description": b.description or "",
                        "webicon": b.webicon or "/static/favicon.ico",
                        "icon_candidates": (
                            b.icon_candidates.split(",")
                            if isinstance(b.icon_candidates, str) and b.icon_candidates
                            else [b.webicon or "/static/favicon.ico"]
                        ),
                        "extra_metadata": json.loads(b.extra_metadata) if b.extra_metadata else {},
                        "tags": [],
                        "is_favorite": bool(b.is_favorite),
                        "created_at": b.created_at.isoformat() if b.created_at else None,
                        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                        "last_used": b.last_used.isoformat() if b.last_used else None,
                        "click_count": int(b.click_count or 0)
                    }
                    for b in untagged_bookmarks
                ]
            }
            result.append(untagged_data)

        # Categorize IP-based bookmarks
        ip_categories = defaultdict(list)
        for bookmark in ip_bookmarks:
            classification, _ = network_detector.classify_url(bookmark.url)
            ip_categories[classification].append(bookmark)

        for classification, bookmarks in ip_categories.items():
            try:
                label = {
                    "Local": "Local Servers",
                    "Local (Offline)": "Local Servers (Offline)",
                    "VPN": "VPN Servers",
                    "Remote": "Remote Servers",
                    "Unknown": "Unknown Servers",
                    "Invalid": "Invalid Servers"
                }.get(classification, "Unknown Servers")
                category_data = {
                    "category_id": len(result),
                    "label": label,
                    "bookmarks": [
                        {
                            "id": int(b.id),
                            "url": b.url or "",
                            "title": b.title or "",
                            "description": b.description or "",
                            "webicon": b.webicon or "/static/favicon.ico",
                            "icon_candidates": (
                                b.icon_candidates.split(",")
                                if isinstance(b.icon_candidates, str) and b.icon_candidates
                                else [b.webicon or "/static/favicon.ico"]
                            ),
                            "extra_metadata": json.loads(b.extra_metadata) if b.extra_metadata else {},
                            "tags": (
                                b.tags.split(",") if isinstance(b.tags, str) and b.tags else []
                            ),
                            "is_favorite": bool(b.is_favorite),
                            "created_at": b.created_at.isoformat() if b.created_at else None,
                            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                            "last_used": b.last_used.isoformat() if b.last_used else None,
                            "click_count": int(b.click_count or 0)
                        }
                        for b in bookmarks
                    ]
                }
                result.append(category_data)
            except Exception as e:
                logger.error(f"Error serializing IP category {classification}: {str(e)}")
                continue

        # Categorize tagged bookmarks
        if tagged_bookmarks:
            tag_categories = defaultdict(list)
            uncategorized_bookmarks = []
            combined_vocab = TAG_VOCAB + USER_TAG_VOCAB

            for bookmark in tagged_bookmarks:
                try:
                    tags = bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
                    tags = [t.strip() for t in tags if t.strip()]
                    domain = urlparse(bookmark.url).netloc
                    domain_type = None
                    for key, value in DOMAIN_TYPES.items():
                        if key in domain:
                            domain_type = value
                            break
                    if domain_type and domain_type not in tags:
                        tags.append(domain_type)

                    # Use the first tag that matches combined_vocab as the primary tag
                    primary_tag = None
                    for tag in tags:
                        if tag in combined_vocab:
                            primary_tag = tag
                            break

                    if primary_tag:
                        tag_categories[primary_tag].append(bookmark)
                    else:
                        uncategorized_bookmarks.append(bookmark)
                except Exception as e:
                    logger.warning(f"Skipping bookmark {bookmark.id} due to tag processing error: {str(e)}")
                    uncategorized_bookmarks.append(bookmark)

            # Add tag-based categories to result
            for tag, bookmarks in tag_categories.items():
                try:
                    category_data = {
                        "category_id": len(result),
                        "label": tag.capitalize(),
                        "bookmarks": [
                            {
                                "id": int(b.id),
                                "url": b.url or "",
                                "title": b.title or "",
                                "description": b.description or "",
                                "webicon": b.webicon or "/static/favicon.ico",
                                "icon_candidates": (
                                    b.icon_candidates.split(",")
                                    if isinstance(b.icon_candidates, str) and b.icon_candidates
                                    else [b.webicon or "/static/favicon.ico"]
                                ),
                                "extra_metadata": json.loads(b.extra_metadata) if b.extra_metadata else {},
                                "tags": (
                                    b.tags.split(",") if isinstance(b.tags, str) and b.tags else []
                                ),
                                "is_favorite": bool(b.is_favorite),
                                "created_at": b.created_at.isoformat() if b.created_at else None,
                                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                                "last_used": b.last_used.isoformat() if b.last_used else None,
                                "click_count": int(b.click_count or 0)
                            }
                            for b in bookmarks
                        ]
                    }
                    result.append(category_data)
                except Exception as e:
                    logger.error(f"Error serializing category for tag {tag}: {str(e)}")
                    continue

            # Categorize remaining bookmarks with K-Means
            if uncategorized_bookmarks:
                texts = []
                valid_bookmarks = []
                for bookmark in uncategorized_bookmarks:
                    try:
                        tag_response = suggest_tags(TagSuggestionRequest(
                            title=bookmark.title or "",
                            description=bookmark.description or "",
                            url=bookmark.url or ""
                        ))
                        tags = tag_response["tags"]
                        domain = urlparse(bookmark.url).netloc
                        text = " ".join([t for t in tags + [bookmark.title or "", bookmark.description or "", domain or ""] if t])
                        if text.strip():
                            texts.append(text.strip())
                            valid_bookmarks.append(bookmark)
                        else:
                            logger.warning(f"Skipping bookmark {bookmark.id} due to empty text")
                    except Exception as e:
                        logger.warning(f"Skipping bookmark {bookmark.id} due to tag suggestion error: {str(e)}")
                        continue

                if texts:
                    try:
                        vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
                        X = vectorizer.fit_transform(texts)
                        logger.info(f"Vectorized {len(texts)} texts with {X.shape[1]} features")
                    except Exception as e:
                        logger.error(f"TF-IDF vectorization failed: {str(e)}")
                        # Skip K-Means and treat as miscellaneous
                        valid_bookmarks = uncategorized_bookmarks
                        labels = [0] * len(valid_bookmarks)
                    else:
                        n_categories = min(max(3, len(valid_bookmarks) // 5), 5, len(texts))
                        try:
                            kmeans = KMeans(n_clusters=n_categories, random_state=42)
                            labels = [int(label) for label in kmeans.fit_predict(X)]
                            logger.info(f"K-Means categorization with labels: {labels}")
                        except Exception as e:
                            logger.error(f"K-Means categorization failed: {str(e)}")
                            labels = [0] * len(valid_bookmarks)

                    # Group uncategorized bookmarks by K-Means labels
                    kmeans_categories = defaultdict(list)
                    for bookmark, label in zip(valid_bookmarks, labels):
                        kmeans_categories[label].append(bookmark)

                    # Label K-Means categories
                    for category_id, bookmarks in kmeans_categories.items():
                        try:
                            all_tags = []
                            domains = []
                            for bookmark in bookmarks:
                                tags = bookmark.tags.split(",") if isinstance(bookmark.tags, str) and bookmark.tags else []
                                all_tags.extend(tags)
                                domain = urlparse(bookmark.url).netloc
                                domains.append(domain)
                                for key, value in DOMAIN_TYPES.items():
                                    if key in domain and value not in all_tags:
                                        all_tags.append(value)
                            tag_counts = Counter(all_tags).most_common(2)
                            domain_counts = Counter([d.split('.')[0] for d in domains]).most_common(1)
                            label_parts = [tag for tag, _ in tag_counts]
                            if domain_counts and domain_counts[0][1] > 1:
                                label_parts.insert(0, domain_counts[0][0].capitalize())
                            label = ", ".join(label_parts) or "Miscellaneous"
                            category_data = {
                                "category_id": len(result),
                                "label": label,
                                "bookmarks": [
                                    {
                                        "id": int(b.id),
                                        "url": b.url or "",
                                        "title": b.title or "",
                                        "description": b.description or "",
                                        "webicon": b.webicon or "/static/favicon.ico",
                                        "icon_candidates": (
                                            b.icon_candidates.split(",")
                                            if isinstance(b.icon_candidates, str) and b.icon_candidates
                                            else [b.webicon or "/static/favicon.ico"]
                                        ),
                                        "extra_metadata": json.loads(b.extra_metadata) if b.extra_metadata else {},
                                        "tags": (
                                            b.tags.split(",") if isinstance(b.tags, str) and b.tags else []
                                        ),
                                        "is_favorite": bool(b.is_favorite),
                                        "created_at": b.created_at.isoformat() if b.created_at else None,
                                        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                                        "last_used": b.last_used.isoformat() if b.last_used else None,
                                        "click_count": int(b.click_count or 0)
                                    }
                                    for b in bookmarks
                                ]
                            }
                            result.append(category_data)
                        except Exception as e:
                            logger.error(f"Error serializing K-Means category {category_id}: {str(e)}")
                            continue

        logger.info(f"Categorized {len(bookmarks)} bookmarks into {len(result)} categories")
        return result
    except Exception as e:
        logger.error(f"Error categorizing bookmarks: {str(e)}", exc_info=True)
        return [{"category_id": 0, "label": "Untagged", "bookmarks": []}]

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
            # Collect user-provided tags for training
            for tag in data["tags"]:
                if tag.strip() and tag not in USER_TAG_VOCAB and tag not in TAG_VOCAB:
                    USER_TAG_VOCAB.append(tag.strip())
                    logger.info(f"Added user tag to USER_TAG_VOCAB: {tag}")
                    # Save the updated USER_TAG_VOCAB to the JSON file
                    try:
                        with USER_TAGS_FILE.open("w") as f:
                            json.dump(USER_TAG_VOCAB, f, indent=2)
                        logger.info(f"Successfully saved updated USER_TAG_VOCAB to {USER_TAGS_FILE}")
                    except IOError as e:
                        logger.error(f"Could not write USER_TAG_VOCAB to {USER_TAGS_FILE}: {e}")
                    except Exception as e:
                        logger.error(f"An unexpected error occurred while saving USER_TAG_VOCAB to {USER_TAGS_FILE}: {e}")
        if "is_favorite" in data:
            bookmark_instance.is_favorite = data["is_favorite"]
        if "url" in data:
            bookmark_instance.url = data["url"]
            # Update network tag for IP-based URLs
            if network_detector.is_ip_url(data["url"]):
                tags = data.get("tags", bookmark_instance.tags.split(",") if bookmark_instance.tags else [])
                network_tag = network_detector.get_network_tag(data["url"])
                if network_tag not in tags:
                    tags.append(network_tag)
                bookmark_instance.tags = ",".join(tags) if tags else None

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
            if isinstance(bookmark_instance.icon_candidates, str)
            and bookmark_instance.icon_candidates
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

        # Serialize bookmark metadata to JSON
        bookmark_data = {
            "id": bookmark_instance.id,
            "url": bookmark_instance.url or "",
            "title": bookmark_instance.title or "",
            "description": bookmark_instance.description or "",
            "webicon": bookmark_instance.webicon or "/static/favicon.ico",
            "icon_candidates": (
                bookmark_instance.icon_candidates.split(",")
                if isinstance(bookmark_instance.icon_candidates, str) and bookmark_instance.icon_candidates
                else [bookmark_instance.webicon or "/static/favicon.ico"]
            ),
            "extra_metadata": json.loads(bookmark_instance.extra_metadata) if bookmark_instance.extra_metadata else {},
            "tags": (
                bookmark_instance.tags.split(",") if isinstance(bookmark_instance.tags, str) and bookmark_instance.tags else []
            ),
            "is_favorite": bool(bookmark_instance.is_favorite),
            "created_at": bookmark_instance.created_at.isoformat() if bookmark_instance.created_at else None,
            "updated_at": bookmark_instance.updated_at.isoformat() if bookmark_instance.updated_at else None,
            "last_used": bookmark_instance.last_used.isoformat() if bookmark_instance.last_used else None,
            "click_count": int(bookmark_instance.click_count or 0),
            "deleted_at": datetime.now().isoformat(),
            "network_classification": network_detector.classify_url(bookmark_instance.url)[0] if network_detector.is_ip_url(bookmark_instance.url) else "N/A"
        }

        # Save metadata to JSON file
        recycled_bookmarks_dir = Path("app/static/recycled_bookmarks")
        recycled_bookmarks_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{bookmark_id}_{timestamp}.json"
        backup_path = recycled_bookmarks_dir / backup_filename
        try:
            with backup_path.open("w") as f:
                json.dump(bookmark_data, f, indent=2)
            logger.info(f"Saved deleted bookmark metadata to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to save deleted bookmark metadata to {backup_path}: {str(e)}")
            # Continue with deletion even if backup fails

        # Move associated icons to recycled_icons
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

        # Delete bookmark from database
        db.delete(bookmark_instance)
        db.commit()
        logger.info(f"Deleted bookmark {bookmark_id} from database")
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
                            logger.info(f"Updated icon_candidates for bookmark {bookmark.id}: {bookmark.icon_candidates}")
                        else:
                            logger.warning(f"Metadata fetch failed for {bookmark.url}: {metadata['error']}")
                            bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for {bookmark.url}: {str(e)}")
                        bookmark.icon_candidates = [bookmark.webicon or "/static/favicon.ico"]
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
        cache_key = f"{request.title}:{request.description}:{request.url}"
        if cache_key in TAG_CACHE:
            logger.info(f"Returning cached tags for {cache_key[:50]}...")
            return {"tags": TAG_CACHE[cache_key]}

        text = f"{request.title} {request.description} {request.url}"
        logger.info(f"Suggesting tags for text: {text[:100]}...")

        # Add domain-based type or network tag
        domain = urlparse(request.url).netloc
        tags = []
        for key, value in DOMAIN_TYPES.items():
            if key in domain:
                tags.append(value)
                break
        if network_detector.is_ip_url(request.url):
            network_tag = network_detector.get_network_tag(request.url)
            tags.append(network_tag)
        text += " " + " ".join(tags)

        # Combine base and user-provided tags
        combined_vocab = TAG_VOCAB + USER_TAG_VOCAB
        vectorizer = TfidfVectorizer(stop_words="english")
        X = vectorizer.fit_transform([text] + combined_vocab)
        similarities = cosine_similarity(X[0:1], X[1:])[0]
        logger.info(f"Similarity scores: {dict(zip(combined_vocab, similarities))}")
        suggested_tags = [
            combined_vocab[i] for i, sim in sorted(enumerate(similarities), key=lambda x: x[1], reverse=True)
            if sim > 0.1
        ][:3]

        # Ensure network tag is included for IP-based URLs
        if network_detector.is_ip_url(request.url) and network_tag not in suggested_tags:
            suggested_tags.append(network_tag)

        TAG_CACHE[cache_key] = suggested_tags
        if len(TAG_CACHE) > 1000:
            TAG_CACHE.pop(next(iter(TAG_CACHE)))

        logger.info(f"Suggested tags: {suggested_tags}")
        return {"tags": suggested_tags}
    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}", exc_info=True)
        return {"tags": [], "message": f"Failed to suggest tags: {str(e)}"}
