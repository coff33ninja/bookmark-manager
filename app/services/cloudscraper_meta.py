import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import logging
from .favicon_generator import download_and_validate_icon, get_icon_type, normalize_url_for_filename, fetch_duckduckgo_favicon, DEFAULT_FAVICON, ICON_DIR

logger = logging.getLogger(__name__)

def fetch_metadata(url: str) -> dict:
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=10, allow_redirects=True)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch {url}: HTTP {response.status_code}")
            return {"error": f"HTTP {response.status_code}"}
        soup = BeautifulSoup(response.content, "html.parser", from_encoding=response.encoding or "utf-8")
        metadata = {"title": "", "description": "", "webicon": DEFAULT_FAVICON, "icon_candidates": []}
        title_tag = (
            soup.find("title") or
            soup.find("meta", property="og:title") or
            soup.find("meta", attrs={"name": "twitter:title"}) or
            soup.find("h1")
        )
        metadata["title"] = title_tag.get_text(strip=True) if title_tag else ""
        description_tag = (
            soup.find("meta", attrs={"name": "description"}) or
            soup.find("meta", property="og:description") or
            soup.find("meta", attrs={"name": "twitter:description"})
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
            ext = os.path.splitext(urlparse(clean_icon_url).path)[1].split("?")[0] or ".png"
            icon_type = get_icon_type(icon_url)
            filename = f"{base_name}_{icon_type}{ext}"
            local_icon_path = ICON_DIR / filename
            static_icon_path = download_and_validate_icon(icon_url, local_icon_path, url)
            if static_icon_path:
                local_candidates.append(static_icon_path)
        if not local_candidates:
            favicon_url = urljoin(url, "/favicon.ico")
            local_icon_path = ICON_DIR / f"{base_name}_favicon.ico"
            static_icon_path = download_and_validate_icon(favicon_url, local_icon_path, url)
            if static_icon_path:
                local_candidates.append(static_icon_path)
        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)
        webicon = (
            next((candidate for candidate in local_candidates if "og-image" in candidate), None) or
            next((candidate for candidate in local_candidates if "apple-touch-icon" in candidate), None) or
            (local_candidates[0] if local_candidates else DEFAULT_FAVICON)
        )
        metadata["webicon"] = webicon
        metadata["icon_candidates"] = local_candidates
        logger.info(f"cloudscraper_meta succeeded for {url}")
        return metadata
    except Exception as e:
        logger.error(f"cloudscraper_meta failed for {url}: {e}")
        return {"error": str(e)}
