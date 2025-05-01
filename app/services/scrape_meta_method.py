import cloudscraper
from urllib.parse import urlparse, urljoin
import os
import logging
from bs4 import BeautifulSoup
from .scrape_meta_style import fetch_html, extract_metadata
from .favicon_generator import download_and_validate_icon, get_icon_type, fetch_duckduckgo_favicon, DEFAULT_FAVICON, ICON_DIR

logger = logging.getLogger(__name__)

def fetch_metadata(url: str) -> dict:
    try:
        scraper = cloudscraper.create_scraper()
        html = fetch_html(url, scraper)
        meta = extract_metadata(html)
        metadata = {"title": meta.get("title", "") or meta.get("og:title", "") or "", "description": meta.get("description", "") or meta.get("og:description", "") or "", "webicon": DEFAULT_FAVICON, "icon_candidates": []}
        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        local_candidates = []

        # Collect all possible icon candidates from the HTML
        icon_candidates = []
        # Standard icons
        for rel in ["icon", "shortcut icon"]:
            for tag in html and extract_metadata(html).get('soup', BeautifulSoup(html, "html.parser")).find_all("link", rel=rel):
                if tag.get("href"):
                    icon_candidates.append(urljoin(url, tag["href"]))
        # Apple touch icon
        for tag in html and extract_metadata(html).get('soup', BeautifulSoup(html, "html.parser")).find_all("link", rel="apple-touch-icon"):
            if tag.get("href"):
                icon_candidates.append(urljoin(url, tag["href"]))
        # Open Graph image
        soup = BeautifulSoup(html, "html.parser")
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            icon_candidates.append(og_image["content"])
        # Fallback to /favicon.ico
        icon_candidates.append(urljoin(url, "/favicon.ico"))
        # Remove duplicates
        seen = set()
        icon_candidates = [x for x in icon_candidates if not (x in seen or seen.add(x))]
        # Try all candidates until one works
        for icon_url in icon_candidates:
            if not icon_url:
                continue
            ext = os.path.splitext(urlparse(icon_url).path)[1].split("?")[0] or ".ico"
            icon_type = get_icon_type(icon_url)
            filename = f"{base_name}_{icon_type}{ext}"
            local_icon_path = ICON_DIR / filename
            static_icon_path = download_and_validate_icon(icon_url, local_icon_path, url, scraper)
            if static_icon_path:
                local_candidates.append(static_icon_path)
                break
        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)
        metadata["webicon"] = local_candidates[0] if local_candidates else DEFAULT_FAVICON
        metadata["icon_candidates"] = local_candidates
        logger.info(f"scrape_meta_method succeeded for {url}")
        return metadata
    except Exception as e:
        logger.error(f"scrape_meta_method failed for {url}: {e}")
        return {"error": str(e)}
