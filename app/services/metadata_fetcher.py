import shutil
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
import io
import zipfile
import logging
from functools import lru_cache
from typing import Optional, Dict, List
import time
import magic
import hashlib

logging.basicConfig(
    level=logging.INFO,
    filename="uvicorn.log",
    filemode="a",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_ICON_DIR = Path("app/static/icons")
DEFAULT_FAVICON = "/static/favicon.ico"
MAX_ICON_SIZE = 1 * 1024 * 1024  # 1MB
TARGET_ICON_SIZE = (64, 64)  # Resize to 64x64 pixels

JS_HEAVY_DOMAINS = ["youtube.com", "youtu.be"]


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
            img.verify()
            img = Image.open(local_path)
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
    icon_url: str, local_path: Path, referer: str, unique_id: str
) -> Optional[str]:
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
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
            logger.warning(
                f"Invalid content-type or extension for {icon_url}: {content_type}, {ext}"
            )
            return None

        content_length = int(resp.headers.get("content-length", 0))
        if content_length > MAX_ICON_SIZE:
            logger.warning(
                f"Icon {icon_url} exceeds size limit: {content_length} bytes"
            )
            return None

        temp_path = local_path.parent / f"{local_path.stem}_{unique_id}.tmp"
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            logger.warning(f"Downloaded icon is empty or missing: {temp_path}")
            if temp_path.exists():
                temp_path.unlink()
            return None

        mime = magic.Magic(mime=True)
        file_type = mime.from_file(str(temp_path))
        if (
            not file_type.startswith("image/")
            or file_type == "application/octet-stream"
        ):
            logger.warning(
                f"Downloaded file is not an image: {temp_path}, MIME: {file_type}"
            )
            temp_path.unlink()
            return None

        try:
            with Image.open(temp_path) as img:
                img.verify()
        except Exception as e:
            logger.error(f"Invalid image file {temp_path}: {e}")
            temp_path.unlink()
            return None

        temp_path.rename(local_path)
        resize_image(local_path)
        logger.info(f"Successfully saved icon: {local_path}")
        return f"/static/icons/{local_path.relative_to(BASE_ICON_DIR)}"
    except Exception as e:
        logger.error(f"Exception downloading icon {icon_url}: {e}")
        if local_path.exists():
            local_path.unlink()
        if temp_path.exists():
            temp_path.unlink()
        return None


def fetch_google_favicon(domain: str) -> str:
    google_url = f"https://www.google.com/s2/favicons?domain={domain}"
    domain_dir = BASE_ICON_DIR / domain.replace(".", "_")
    domain_dir.mkdir(parents=True, exist_ok=True)
    local_icon_path = domain_dir / "google.ico"
    unique_id = hashlib.md5(google_url.encode()).hexdigest()[:8]
    static_path = download_and_validate_icon(google_url, local_icon_path, "", unique_id)
    return static_path or DEFAULT_FAVICON


def fetch_duckduckgo_favicon(domain: str) -> str:
    duckduckgo_url = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
    domain_dir = BASE_ICON_DIR / domain.replace(".", "_")
    domain_dir.mkdir(parents=True, exist_ok=True)
    local_icon_path = domain_dir / "duckduckgo.ico"
    unique_id = hashlib.md5(duckduckgo_url.encode()).hexdigest()[:8]
    static_path = download_and_validate_icon(
        duckduckgo_url, local_icon_path, "", unique_id
    )
    return static_path or DEFAULT_FAVICON


def fetch_html(url: str, scraper: cloudscraper.CloudScraper, timeout: int = 15) -> str:
    try:
        resp = scraper.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error(f"Failed to fetch HTML for {url}: {e}")
        raise


def extract_metadata(html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
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
        domain_dir = BASE_ICON_DIR / base_name
        domain_dir.mkdir(parents=True, exist_ok=True)
        local_candidates = []
        seen_files = set()

        soup = BeautifulSoup(html, "html.parser")
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

        for idx, icon_url in enumerate(icon_candidates):
            if not icon_url:
                continue
            clean_icon_url = normalize_url_for_filename(icon_url)
            ext = (
                os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                or ".png"
            )
            icon_type = get_icon_type(icon_url)
            filename = f"{icon_type}_{idx}{ext}"
            local_icon_path = domain_dir / filename
            unique_id = hashlib.md5(icon_url.encode()).hexdigest()[:8]
            static_icon_path = download_and_validate_icon(
                icon_url, local_icon_path, url, unique_id
            )
            if static_icon_path and static_icon_path not in seen_files:
                local_candidates.append(static_icon_path)
                seen_files.add(static_icon_path)

        if not local_candidates and meta.get("favicon"):
            favicon_url = urljoin(url, meta["favicon"])
            local_icon_path = domain_dir / f"favicon{ext}"
            unique_id = hashlib.md5(favicon_url.encode()).hexdigest()[:8]
            static_icon_path = download_and_validate_icon(
                favicon_url, local_icon_path, url, unique_id
            )
            if static_icon_path and static_icon_path not in seen_files:
                local_candidates.append(static_icon_path)
                seen_files.add(static_icon_path)

        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON and duckduckgo_icon not in seen_files:
                local_candidates.append(duckduckgo_icon)
                seen_files.add(duckduckgo_icon)

        if not local_candidates:
            domain = parsed.netloc
            google_icon = fetch_google_favicon(domain)
            if google_icon != DEFAULT_FAVICON and google_icon not in seen_files:
                local_candidates.append(google_icon)
                seen_files.add(google_icon)

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
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
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
        seen = set()
        icon_candidates = [x for x in icon_candidates if not (x in seen or seen.add(x))]

        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        domain_dir = BASE_ICON_DIR / base_name
        domain_dir.mkdir(parents=True, exist_ok=True)
        local_candidates = []
        seen_files = set()

        for idx, icon_url in enumerate(icon_candidates):
            if not icon_url:
                continue
            clean_icon_url = normalize_url_for_filename(icon_url)
            ext = (
                os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                or ".png"
            )
            icon_type = get_icon_type(icon_url)
            filename = f"{icon_type}_{idx}{ext}"
            local_icon_path = domain_dir / filename
            unique_id = hashlib.md5(icon_url.encode()).hexdigest()[:8]
            static_icon_path = download_and_validate_icon(
                icon_url, local_icon_path, url, unique_id
            )
            if static_icon_path and static_icon_path not in seen_files:
                local_candidates.append(static_icon_path)
                seen_files.add(static_icon_path)

        if not local_candidates:
            favicon_url = urljoin(url, "/favicon.ico")
            local_icon_path = domain_dir / "favicon.ico"
            unique_id = hashlib.md5(favicon_url.encode()).hexdigest()[:8]
            static_icon_path = download_and_validate_icon(
                favicon_url, local_icon_path, url, unique_id
            )
            if static_icon_path and static_icon_path not in seen_files:
                local_candidates.append(static_icon_path)
                seen_files.add(static_icon_path)

        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON and duckduckgo_icon not in seen_files:
                local_candidates.append(duckduckgo_icon)
                seen_files.add(duckduckgo_icon)

        if not local_candidates:
            domain = parsed.netloc
            google_icon = fetch_google_favicon(domain)
            if google_icon != DEFAULT_FAVICON and google_icon not in seen_files:
                local_candidates.append(google_icon)
                seen_files.add(google_icon)

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


def fetch_metadata_with_selenium(url: str, retries: int = 2) -> Dict:
    for attempt in range(retries):
        try:
            driver_path = setup_geckodriver()
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            service = Service(driver_path)
            with webdriver.Firefox(service=service, options=options) as driver:
                driver.set_page_load_timeout(30)
                driver.get(url)
                time.sleep(5)
                soup = BeautifulSoup(driver.page_source, "html.parser")
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
                icon_candidates = [
                    x for x in icon_candidates if not (x in seen or seen.add(x))
                ]

                parsed = urlparse(url)
                base_name = parsed.netloc.replace(".", "_")
                domain_dir = BASE_ICON_DIR / base_name
                domain_dir.mkdir(parents=True, exist_ok=True)
                local_candidates = []
                seen_files = set()

                for idx, icon_url in enumerate(icon_candidates):
                    if not icon_url:
                        continue
                    clean_icon_url = normalize_url_for_filename(icon_url)
                    ext = (
                        os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0]
                        or ".png"
                    )
                    icon_type = get_icon_type(icon_url)
                    filename = f"{icon_type}_{idx}{ext}"
                    local_icon_path = domain_dir / filename
                    unique_id = hashlib.md5(icon_url.encode()).hexdigest()[:8]
                    static_icon_path = download_and_validate_icon(
                        icon_url, local_icon_path, url, unique_id
                    )
                    if static_icon_path and static_icon_path not in seen_files:
                        local_candidates.append(static_icon_path)
                        seen_files.add(static_icon_path)

                if not local_candidates:
                    favicon_url = urljoin(url, "/favicon.ico")
                    local_icon_path = domain_dir / "favicon.ico"
                    unique_id = hashlib.md5(favicon_url.encode()).hexdigest()[:8]
                    static_icon_path = download_and_validate_icon(
                        favicon_url, local_icon_path, url, unique_id
                    )
                    if static_icon_path and static_icon_path not in seen_files:
                        local_candidates.append(static_icon_path)
                        seen_files.add(static_icon_path)

                if not local_candidates:
                    domain = parsed.netloc
                    duckduckgo_icon = fetch_duckduckgo_favicon(domain)
                    if (
                        duckduckgo_icon != DEFAULT_FAVICON
                        and duckduckgo_icon not in seen_files
                    ):
                        local_candidates.append(duckduckgo_icon)
                        seen_files.add(duckduckgo_icon)

                if not local_candidates:
                    domain = parsed.netloc
                    google_icon = fetch_google_favicon(domain)
                    if google_icon != DEFAULT_FAVICON and google_icon not in seen_files:
                        local_candidates.append(google_icon)
                        seen_files.add(google_icon)

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
                logger.info(f"Fetched metadata with Selenium for {url}: {metadata}")
                return metadata
        except Exception as e:
            logger.error(
                f"Error fetching metadata with Selenium for {url} (attempt {attempt + 1}/{retries}): {str(e)}"
            )
            if attempt + 1 == retries:
                return {"error": str(e)}
            time.sleep(2)
    return {"error": "Selenium retries exhausted"}


def setup_geckodriver():
    url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win64.zip"
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


def is_valid_metadata(metadata: Dict) -> bool:
    if "error" in metadata:
        return False
    title = metadata.get("title", "").lower()
    invalid_phrases = [
        "update your browser",
        "browser not supported",
        "javascript required",
    ]
    if any(phrase in title for phrase in invalid_phrases):
        return False
    return (
        metadata.get("title")
        or metadata.get("description")
        or metadata.get("webicon") != DEFAULT_FAVICON
        or any(metadata.get("extra_metadata", {}).values())
    )

def fetch_metadata_combined(url: str) -> Dict:
    try:
        logger.info(f"Starting metadata fetch for URL: {url}")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace(".", "_")
        base_dir = Path("app/static/icons") / domain
        base_dir.mkdir(parents=True, exist_ok=True)
        recycle_dir = Path("app/static/recycled_icons") / domain

        # Check recycled icons
        recycled_icons = []
        if recycle_dir.exists():
            for icon_path in recycle_dir.glob("*"):
                if icon_path.is_file():
                    relative_path = f"/static/recycled_icons/{domain}/{icon_path.name}"
                    recycled_icons.append(relative_path)
            if recycled_icons:
                logger.info(f"Found {len(recycled_icons)} recycled icons for {domain}: {recycled_icons}")
                webicon = recycled_icons[0]
                for recycled_icon in recycled_icons:
                    src_path = Path("app") / recycled_icon.lstrip("/")
                    dest_path = base_dir / src_path.name
                    if not dest_path.exists():
                        shutil.move(str(src_path), str(dest_path))
                        logger.info(f"Moved recycled icon {src_path} to {dest_path}")
                return {
                    "title": "Reused bookmark",
                    "description": "",
                    "webicon": f"/static/icons/{domain}/{Path(recycled_icons[0]).name}",
                    "icon_candidates": [f"/static/icons/{domain}/{Path(ic).name}" for ic in recycled_icons],
                    "extra_metadata": {"url": url}
                }

        scraper = cloudscraper.create_scraper()
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return {"error": f"Failed to fetch URL: {str(e)}"}

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title else "No title"
        logger.info(f"Extracted title: {title}")

        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()
        logger.info(f"Extracted description: {description[:50]}...")

        icon_candidates = []
        webicon = None
        icons = []

        # Prioritize high-res icons
        apple_icon = soup.find("link", rel="apple-touch-icon")
        if apple_icon and apple_icon.get("href"):
            icons.append(("apple-touch-icon", apple_icon["href"]))
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image["content"]:
            icons.append(("og-image", og_image["content"]))
        favicon = soup.find("link", rel="icon") or soup.find("link", rel="shortcut icon")
        if favicon and favicon.get("href"):
            icons.append(("favicon", favicon["href"]))

        mime = magic.Magic(mime=True)
        for idx, (icon_type, icon_url) in enumerate(icons):
            try:
                absolute_icon_url = urljoin(url, icon_url)
                icon_response = scraper.get(absolute_icon_url, timeout=5)
                icon_response.raise_for_status()
                content_type = icon_response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning(f"Skipping non-image content for {absolute_icon_url}: {content_type}")
                    continue

                # Determine file extension and suitability
                file_mime = mime.from_buffer(icon_response.content)
                file_ext = file_mime.split("/")[-1].lower()
                if file_ext == "x-icon":
                    file_ext = "ico"
                elif file_ext not in ["png", "jpeg", "jpg"]:
                    file_ext = "png"

                # Check if icon can be preserved as-is
                preserve_original = False
                if file_mime in ["image/png", "image/x-icon"]:
                    try:
                        img = Image.open(io.BytesIO(icon_response.content))
                        img.verify()
                        img = Image.open(io.BytesIO(icon_response.content))  # Reopen for size check
                        width, height = img.size
                        if 16 <= width <= 180 and 16 <= height <= 180:
                            preserve_original = True
                            logger.info(f"Preserving original {file_mime} for {absolute_icon_url} (size: {width}x{height})")
                    except Exception as e:
                        logger.warning(f"Failed to verify image size for {absolute_icon_url}: {str(e)}")

                icon_path = base_dir / f"icon_{idx}.{file_ext}"
                if preserve_original:
                    # Save original content
                    with open(icon_path, "wb") as f:
                        f.write(icon_response.content)
                    logger.info(f"Saved original icon: {icon_path}")
                else:
                    # Process with PIL
                    img = Image.open(io.BytesIO(icon_response.content))
                    img.verify()
                    img = Image.open(io.BytesIO(icon_response.content))  # Reopen for processing
                    if img.mode not in ["RGB", "RGBA"]:
                        img = img.convert("RGBA" if "A" in img.mode else "RGB")
                    if max(img.size) > 128:
                        img = img.resize((128, 128), Image.Resampling.LANCZOS)
                    img.save(icon_path, "PNG", quality=95)
                    logger.info(f"Saved processed icon: {icon_path}")

                relative_path = f"/static/icons/{domain}/{icon_path.name}"
                icon_candidates.append(relative_path)
                if not webicon and icon_type in ["apple-touch-icon", "og-image"]:
                    webicon = relative_path
            except Exception as e:
                logger.warning(f"Failed to process icon {icon_url}: {str(e)}")
                continue

        if not icon_candidates:
            logger.warning(f"No valid icons found for {url}")
            webicon = "/static/favicon.ico"
            icon_candidates = [webicon]

        if not webicon:
            webicon = icon_candidates[0]

        return {
            "title": title,
            "description": description,
            "webicon": webicon,
            "icon_candidates": icon_candidates,
            "extra_metadata": {
                "og_title": soup.find("meta", attrs={"property": "og:title"})["content"] if soup.find("meta", attrs={"property": "og:title"}) else None,
                "url": url
            }
        }
    except Exception as e:
        logger.error(f"Metadata fetch failed for {url}: {str(e)}", exc_info=True)
        return {
            "error": f"Metadata fetch failed: {str(e)}",
            "title": "No title",
            "description": "",
            "webicon": "/static/favicon.ico",
            "icon_candidates": [],
            "extra_metadata": {}
        }
