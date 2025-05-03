import requests
import cloudscraper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from PIL import Image
from urllib.parse import urlparse, urljoin, urlunparse
from pathlib import Path
import os
import zipfile
import logging
from functools import lru_cache
from typing import Optional, Dict, List
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ICON_DIR = Path("app/static/icons")
DEFAULT_FAVICON = "/static/favicon.ico"
MAX_ICON_SIZE = 1 * 1024 * 1024  # 1MB
TARGET_ICON_SIZE = (64, 64)  # Resize to 64x64 pixels


def normalize_url_for_filename(icon_url: str) -> str:
    parsed = urlparse(icon_url)
    clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return clean_url


def get_icon_type(icon_url: str) -> str:
    icon_url_lower = icon_url.lower()
    if "apple-touch-icon" in icon_url_lower:
        return "apple-touch-icon"
    elif "og:image" in icon_url_lower:
        return "og-image"
    elif "favicon" in icon_url_lower:
        return "favicon"
    return "other"


def is_valid_image(content_type: str, ext: str) -> bool:
    valid_extensions = [".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp"]
    return content_type.startswith("image/") and ext.lower() in valid_extensions


def resize_image(local_path: Path):
    try:
        with Image.open(local_path) as img:
            img.verify()  # Verify image integrity
            img = Image.open(local_path)  # Re-open after verify
            if img.size[0] > TARGET_ICON_SIZE[0] or img.size[1] > TARGET_ICON_SIZE[1]:
                img.thumbnail(TARGET_ICON_SIZE)
                img.save(local_path)
                logger.info(f"Resized image to {TARGET_ICON_SIZE}: {local_path}")
    except Exception as e:
        logger.error(f"Failed to resize image {local_path}: {e}")
        if local_path.exists():
            local_path.unlink()
        raise


def download_and_validate_icon(
    icon_url: str, local_path: Path, referer: str
) -> Optional[str]:
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer,
                "Accept": "image/*,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        resp = session.get(icon_url, timeout=20, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"Failed to download {icon_url}: HTTP {resp.status_code}")
            return None

        content_type = resp.headers.get("content-type", "").lower()
        ext = os.path.splitext(urlparse(icon_url).path)[1].split("?")[0] or ".png"
        if not is_valid_image(content_type, ext):
            logger.warning(f"Invalid content-type or extension for {icon_url}")
            return None

        content_length = int(resp.headers.get("content-length", 0))
        if content_length > MAX_ICON_SIZE:
            logger.warning(
                f"Icon {icon_url} exceeds size limit: {content_length} bytes"
            )
            return None

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        if local_path.exists() and local_path.stat().st_size > 0:
            try:
                with Image.open(local_path) as img:
                    img.verify()  # Ensure it's a valid image
                resize_image(local_path)
                return f"/static/icons/{local_path.name}"
            except Exception as e:
                logger.error(f"Invalid image file {local_path}: {e}")
                local_path.unlink()
                return None
        else:
            logger.warning(f"Downloaded icon is empty or missing: {local_path}")
            if local_path.exists():
                local_path.unlink()
            return None
    except Exception as e:
        logger.error(f"Exception downloading icon {icon_url}: {e}")
        return None


def fetch_duckduckgo_favicon(domain: str) -> str:
    duckduckgo_url = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
    local_icon_path = ICON_DIR / f"{domain.replace('.', '_')}_duckduckgo.ico"
    static_path = download_and_validate_icon(duckduckgo_url, local_icon_path, "")
    return static_path or DEFAULT_FAVICON


def fetch_html(url: str, scraper: cloudscraper.CloudScraper, timeout: int = 15) -> str:
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
    elif h1_tag := soup.find("h1"):
        data["title"] = h1_tag.get_text(strip=True)

    if desc := soup.find("meta", attrs={"name": "description"}):
        data["description"] = desc.get("content", "").strip()
    elif og_desc := soup.find("meta", property="og:description"):
        data["description"] = og_desc.get("content", "").strip()

    for prop in ("og:title", "og:site_name", "og:description"):
        if tag := soup.find("meta", property=prop):
            data[prop] = tag.get("content", "").strip()

    if icon := soup.find("link", rel=lambda x: x and "icon" in x.lower()):
        data["favicon"] = icon.get("href")

    return data


@lru_cache(maxsize=1000)
def fetch_metadata_scrape_meta(url: str) -> Dict:
    """Fetch metadata using scrape_meta.py's approach with Bookmarks Manager's icon handling."""
    try:
        scraper = cloudscraper.create_scraper()
        html = fetch_html(url, scraper)
        meta = extract_metadata(html)
        metadata = {
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "webicon": DEFAULT_FAVICON,
            "icon_candidates": [],
            "extra_metadata": {
                "og:title": meta.get("og:title"),
                "og:site_name": meta.get("og:site_name"),
                "og:description": meta.get("og:description"),
            },
        }

        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        local_candidates = []

        # Collect icon candidates (enhanced from scrape_meta.py)
        soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
        icon_candidates = []
        for rel in ["icon", "shortcut icon"]:
            for tag in soup.find_all("link", rel=rel):
                if tag.get("href"):
                    icon_candidates.append(urljoin(url, tag["href"]))
        for tag in soup.find_all("link", rel="apple-touch-icon"):
            if tag.get("href"):
                icon_candidates.append(urljoin(url, tag["href"]))
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            icon_candidates.append(og_image["content"])
        icon_candidates.append(urljoin(url, "/favicon.ico"))
        seen = set()
        icon_candidates = [x for x in icon_candidates if not (x in seen or seen.add(x))]

        # Process icon candidates
        for icon_url in icon_candidates:
            if not icon_url:
                continue
            clean_icon_url = normalize_url_for_filename(icon_url)
            ext = (
                os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                or ".png"
            )
            icon_type = get_icon_type(icon_url)
            filename = f"{base_name}_{icon_type}{ext}"
            local_icon_path = ICON_DIR / filename
            static_icon_path = download_and_validate_icon(
                icon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        # Fallback to /favicon.ico
        if not local_candidates and meta.get("favicon"):
            favicon_url = urljoin(url, meta["favicon"])
            local_icon_path = ICON_DIR / f"{base_name}_favicon{ext}"
            static_icon_path = download_and_validate_icon(
                favicon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        # Fallback to DuckDuckGo
        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)

        webicon = (
            next(
                (
                    candidate
                    for candidate in local_candidates
                    if "og-image" in candidate
                ),
                None,
            )
            or next(
                (
                    candidate
                    for candidate in local_candidates
                    if "apple-touch-icon" in candidate
                ),
                None,
            )
            or (local_candidates[0] if local_candidates else DEFAULT_FAVICON)
        )

        metadata["webicon"] = webicon
        metadata["icon_candidates"] = local_candidates
        logger.info(f"Fetched metadata for {url} using scrape_meta: {metadata}")
        return metadata
    except Exception as e:
        logger.error(f"Error fetching metadata for {url} using scrape_meta: {str(e)}")
        return {"error": str(e)}


@lru_cache(maxsize=1000)
def fetch_metadata_cloudscraper(url: str) -> Dict:
    """Existing cloudscraper-based metadata fetching."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=10,
            allow_redirects=True,
        )
        if response.status_code != 200:
            logger.warning(f"Failed to fetch {url}: HTTP {response.status_code}")
            return {"error": f"HTTP {response.status_code}"}

        soup = BeautifulSoup(
            response.content, "html.parser", from_encoding=response.encoding or "utf-8"
        )
        metadata = {
            "title": "",
            "description": "",
            "webicon": DEFAULT_FAVICON,
            "icon_candidates": [],
        }

        title_tag = (
            soup.find("title")
            or soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
            or soup.find("h1")
        )
        metadata["title"] = title_tag.get_text(strip=True) if title_tag else ""

        description_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "twitter:description"})
        )
        metadata["description"] = (
            description_tag["content"]
            if description_tag and description_tag.get("content")
            else ""
        )

        icon_candidates = []
        for rel in ["icon", "shortcut icon"]:
            for tag in soup.find_all("link", rel=rel):
                if tag.get("href"):
                    icon_candidates.append(urljoin(url, tag["href"]))
        for tag in soup.find_all("link", rel="apple-touch-icon"):
            if tag.get("href"):
                icon_candidates.append(urljoin(url, tag["href"]))
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            icon_candidates.append(og_image["content"])
        icon_candidates.append(urljoin(url, "/favicon.ico"))
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                icon_candidates.append(urljoin(url, src))
        seen = set()
        icon_candidates = [x for x in icon_candidates if not (x in seen or seen.add(x))]

        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        local_candidates = []

        for icon_url in icon_candidates:
            if not icon_url:
                continue
            clean_icon_url = normalize_url_for_filename(icon_url)
            ext = (
                os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                or ".png"
            )
            icon_type = get_icon_type(icon_url)
            filename = f"{base_name}_{icon_type}{ext}"
            local_icon_path = ICON_DIR / filename
            static_icon_path = download_and_validate_icon(
                icon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        if not local_candidates:
            favicon_url = urljoin(url, "/favicon.ico")
            local_icon_path = ICON_DIR / f"{base_name}_favicon.ico"
            static_icon_path = download_and_validate_icon(
                favicon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)

        webicon = (
            next(
                (
                    candidate
                    for candidate in local_candidates
                    if "og-image" in candidate
                ),
                None,
            )
            or next(
                (
                    candidate
                    for candidate in local_candidates
                    if "apple-touch-icon" in candidate
                ),
                None,
            )
            or (local_candidates[0] if local_candidates else DEFAULT_FAVICON)
        )

        metadata["webicon"] = webicon
        metadata["icon_candidates"] = local_candidates
        logger.info(f"Fetched metadata for {url} using cloudscraper: {metadata}")
        return metadata
    except Exception as e:
        logger.error(f"Error fetching metadata for {url} using cloudscraper: {str(e)}")
        return {"error": str(e)}


def fetch_metadata_with_selenium(url: str) -> Dict:
    """Existing Selenium-based metadata fetching."""
    try:
        driver_path = setup_geckodriver()
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        service = Service(driver_path)
        driver = webdriver.Firefox(service=service, options=options)
        driver.get(url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser", from_encoding="utf-8")
        metadata = {
            "title": "",
            "description": "",
            "webicon": DEFAULT_FAVICON,
            "icon_candidates": [],
        }

        title_tag = (
            soup.find("title")
            or soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
            or soup.find("h1")
        )
        metadata["title"] = title_tag.get_text(strip=True) if title_tag else ""

        description_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "twitter:description"})
        )
        metadata["description"] = (
            description_tag["content"]
            if description_tag and description_tag.get("content")
            else ""
        )

        icon_candidates = []
        for rel in ["icon", "shortcut icon"]:
            for tag in soup.find_all("link", rel=rel):
                if tag.get("href"):
                    icon_candidates.append(urljoin(url, tag["href"]))
        for tag in soup.find_all("link", rel="apple-touch-icon"):
            if tag.get("href"):
                icon_candidates.append(urljoin(url, tag["href"]))
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            icon_candidates.append(og_image["content"])
        icon_candidates.append(urljoin(url, "/favicon.ico"))
        seen = set()
        icon_candidates = [x for x in icon_candidates if not (x in seen or seen.add(x))]

        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        local_candidates = []

        for icon_url in icon_candidates:
            if not icon_url:
                continue
            clean_icon_url = normalize_url_for_filename(icon_url)
            ext = (
                os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                or ".png"
            )
            icon_type = get_icon_type(icon_url)
            filename = f"{base_name}_{icon_type}{ext}"
            local_icon_path = ICON_DIR / filename
            static_icon_path = download_and_validate_icon(
                icon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        if not local_candidates:
            favicon_url = urljoin(url, "/favicon.ico")
            local_icon_path = ICON_DIR / f"{base_name}_favicon.ico"
            static_icon_path = download_and_validate_icon(
                favicon_url, local_icon_path, url
            )
            if static_icon_path:
                local_candidates.append(static_icon_path)

        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)

        webicon = (
            next(
                (
                    candidate
                    for candidate in local_candidates
                    if "og-image" in candidate
                ),
                None,
            )
            or next(
                (
                    candidate
                    for candidate in local_candidates
                    if "apple-touch-icon" in candidate
                ),
                None,
            )
            or (local_candidates[0] if local_candidates else DEFAULT_FAVICON)
        )

        metadata["webicon"] = webicon
        metadata["icon_candidates"] = local_candidates
        driver.quit()
        logger.info(f"Fetched metadata with Selenium for {url}: {metadata}")
        return metadata
    except Exception as e:
        logger.error(f"Error fetching metadata with Selenium for {url}: {str(e)}")
        return {"error": str(e)}


def setup_geckodriver():
    url = "https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-win32.zip"
    driver_dir = "drivers"
    driver_path = os.path.join(driver_dir, "geckodriver.exe")
    if not os.path.exists(driver_path):
        os.makedirs(driver_dir, exist_ok=True)
        response = requests.get(url, stream=True)
        zip_path = os.path.join(driver_dir, "geckodriver.zip")
        with open(zip_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=128):
                file.write(chunk)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(driver_dir)
        os.remove(zip_path)
    return driver_path


def fetch_metadata_combined(url: str) -> Dict:
    """Try metadata fetching methods in order: scrape_meta, cloudscraper, selenium."""
    methods = [
        ("scrape_meta", fetch_metadata_scrape_meta),
        ("cloudscraper", fetch_metadata_cloudscraper),
        ("selenium", fetch_metadata_with_selenium),
    ]

    for method_name, fetch_func in methods:
        metadata = fetch_func(url)
        if "error" not in metadata and (
            metadata.get("title")
            or metadata.get("description")
            or metadata.get("webicon") != DEFAULT_FAVICON
        ):
            logger.info(f"Successfully fetched metadata for {url} using {method_name}")
            return metadata
        logger.warning(f"Method {method_name} failed for {url}, trying next method")

    logger.error(f"All metadata fetching methods failed for {url}")
    return {
        "title": "No title",
        "description": "",
        "webicon": DEFAULT_FAVICON,
        "icon_candidates": [],
        "error": "All fetching methods failed",
    }
