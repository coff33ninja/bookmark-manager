import logging
from functools import lru_cache
from typing import Dict

from bs4 import BeautifulSoup

from .scrape_meta_style import fetch_metadata as fetch_scrape_meta_style
from .scrape_meta_method import fetch_metadata as fetch_scrape_meta_method
from .cloudscraper_meta import fetch_metadata as fetch_cloudscraper_meta
from .selenium_meta import fetch_metadata as fetch_selenium_meta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_ICON_SIZE = 1 * 1024 * 1024  # 1MB
TARGET_ICON_SIZE = (64, 64)  # Resize to 64x64 pixels

def fetch_html(url: str, scraper, timeout=15) -> str:
    """Fetch page HTML using Cloudscraper (from scrape_meta.py)."""
    try:
        resp = scraper.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error(f"Failed to fetch HTML for {url}: {e}")
        raise

def extract_metadata(html: str) -> Dict:
    """Extract common metadata into a dict (from scrape_meta.py)."""
    try:
        soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
        data = {
            "title": None,
            "description": None,
            "og:title": None,
            "og:site_name": None,
            "og:description": None,
            "favicon": None,
        }

        if title_tag := soup.find("title"):
            data["title"] = title_tag.get_text(strip=True)
        elif og_title := soup.find("meta", property="og:title"):
            data["title"] = og_title.get("content", "").strip()
        elif twitter_title := soup.find("meta", attrs={"name": "twitter:title"}):
            data["title"] = twitter_title.get("content", "").strip()
        elif h1_tag := soup.find("h1"):
            data["title"] = h1_tag.get_text(strip=True)

        if desc := soup.find("meta", attrs={"name": "description"}):
            data["description"] = desc.get("content", "").strip()
        elif og_desc := soup.find("meta", property="og:description"):
            data["description"] = og_desc.get("content", "").strip()
        elif twitter_desc := soup.find("meta", attrs={"name": "twitter:description"}):
            data["description"] = twitter_desc.get("content", "").strip()

        for prop in ("og:title", "og:site_name", "og:description"):
            if tag := soup.find("meta", property=prop):
                data[prop] = tag.get("content", "").strip()

        if icon := soup.find("link", rel=lambda x: x and "icon" in x.lower()):
            data["favicon"] = icon.get("href")
        elif apple_icon := soup.find("link", rel="apple-touch-icon"):
            data["favicon"] = apple_icon.get("href")
        elif og_image := soup.find("meta", property="og:image"):
            data["favicon"] = og_image.get("content")

        return data
    except Exception as e:
        logger.error(f"Error extracting metadata: {e}")
        return {"error": str(e)}

@lru_cache(maxsize=1000)
def fetch_metadata_combined(url: str) -> Dict:
    """Try scrape_meta style first, then fallback to other methods."""
    metadata = fetch_metadata_with_fallbacks(url)
    return metadata

def fetch_metadata_with_fallbacks(url: str) -> dict:
    """
    Try each metadata extraction method in order. Return the first successful result, or an error if all fail.
    """
    attempts = [
        ("scrape_meta_style", fetch_scrape_meta_style),
        ("scrape_meta_method", fetch_scrape_meta_method),
        ("cloudscraper_meta", fetch_cloudscraper_meta),
        ("selenium_meta", fetch_selenium_meta),
    ]
    for name, func in attempts:
        try:
            metadata = func(url)
            if metadata and not metadata.get("error") and (
                metadata.get("title") or metadata.get("description") or metadata.get("webicon")
            ):
                logger.info(f"{name} succeeded for {url}")
                return metadata
            else:
                logger.warning(f"{name} failed or returned empty metadata for {url}")
        except Exception as e:
            logger.error(f"{name} raised exception for {url}: {e}")
    logger.error(f"All metadata extraction attempts failed for {url}")
    return {"error": "All metadata extraction attempts failed"}