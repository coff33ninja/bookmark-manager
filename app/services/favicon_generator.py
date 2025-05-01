from pathlib import Path
import os
import requests
import logging
from urllib.parse import urlparse, urlunparse
from typing import Optional
from PIL import Image, ImageDraw

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
            img.verify()  # Validate image
            img = Image.open(local_path)  # Reopen after verify
            if img.size[0] > TARGET_ICON_SIZE[0] or img.size[1] > TARGET_ICON_SIZE[1]:
                img.thumbnail(TARGET_ICON_SIZE)
                img.save(local_path)
                logger.info(f"Resized image to {TARGET_ICON_SIZE}: {local_path}")
    except Exception as e:
        logger.error(f"Failed to resize image {local_path}: {e}")
        if local_path.exists():
            local_path.unlink()

def download_and_validate_icon(icon_url: str, local_path: Path, referer: str, scraper=None) -> Optional[str]:
    try:
        if scraper is not None:
            session = scraper
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer,
                "Accept": "image/*,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = session.get(icon_url, timeout=20, stream=True, allow_redirects=True, headers=headers)
        else:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer,
                "Accept": "image/*,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            })
            resp = session.get(icon_url, timeout=20, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"Failed to download {icon_url}: HTTP {resp.status_code}")
            return None
        content_type = resp.headers.get("content-type", "").lower()
        ext = os.path.splitext(urlparse(icon_url).path)[1].split("?")[0] or ".png"
        valid_extensions = [".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp"]
        if not (content_type.startswith("image/") or ext.lower() in valid_extensions):
            logger.warning(f"Invalid content-type or extension for {icon_url}")
            return None
        content_length = int(resp.headers.get("content-length", 0))
        if content_length > MAX_ICON_SIZE:
            logger.warning(f"Icon {icon_url} exceeds size limit: {content_length} bytes")
            return None
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        if local_path.exists() and local_path.stat().st_size > 0:
            # Only try PIL validation for types PIL can handle
            if ext.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                try:
                    with Image.open(local_path) as img:
                        img.verify()  # Ensure it's a valid image
                    resize_image(local_path)
                except Exception as e:
                    logger.warning(f"PIL could not verify image {local_path}: {e} (keeping file anyway)")
            # For .ico, .svg, etc., just keep the file
            return f"/static/icons/{local_path.name}"
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

def generate_favicon(output_path="app/static/favicon.ico"):
    size = (64, 64)
    image = Image.new("RGBA", size, "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill="blue")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    image.save(output_path, format="ICO")

if __name__ == "__main__":
    generate_favicon()
    print("Favicon generated at app/static/favicon.ico")
