import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import logging
import argparse
import json
import sys

try:
    from .favicon_generator import (
        download_and_validate_icon,
        get_icon_type,
        fetch_duckduckgo_favicon,
        DEFAULT_FAVICON,
        ICON_DIR,
    )
except ImportError:
    from favicon_generator import (
        download_and_validate_icon,
        get_icon_type,
        fetch_duckduckgo_favicon,
        DEFAULT_FAVICON,
        ICON_DIR,
    )

logger = logging.getLogger(__name__)

def fetch_html(url: str, scraper, timeout=15) -> str:
    resp = scraper.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text

def extract_metadata(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
    data = {"title": None, "description": None, "og:title": None, "og:site_name": None, "og:description": None, "favicon": None}
    if title_tag := soup.find("title"):
        data["title"] = title_tag.get_text(strip=True)
    if desc := soup.find("meta", attrs={"name": "description"}):
        data["description"] = desc.get("content", "").strip()
    for prop in ("og:title", "og:site_name", "og:description"):
        if tag := soup.find("meta", property=prop):
            data[prop] = tag.get("content", "").strip()
    if icon := soup.find("link", rel=lambda x: x and "icon" in x.lower()):
        data["favicon"] = icon.get("href")
    return data

def fetch_metadata(url: str) -> dict:
    try:
        scraper = cloudscraper.create_scraper()
        html = fetch_html(url, scraper)
        meta = extract_metadata(html)
        metadata = {
            "title": meta.get("title", "") or meta.get("og:title", "") or "",
            "description": meta.get("description", "") or meta.get("og:description", "") or "",
            "webicon": DEFAULT_FAVICON,
            "icon_candidates": []
        }
        parsed = urlparse(url)
        base_name = parsed.netloc.replace(".", "_")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        local_candidates = []

        # Parse HTML once
        soup = BeautifulSoup(html, "html.parser")

        # Collect all possible icon candidates from the HTML
        icon_candidates = []
        # Standard icons
        for rel in ["icon", "shortcut icon"]:
            for tag in soup.find_all("link", rel=rel):
                if tag.get("href"):
                    icon_candidates.append(urljoin(url, tag["href"]))
        # Apple touch icon
        for tag in soup.find_all("link", rel="apple-touch-icon"):
            if tag.get("href"):
                icon_candidates.append(urljoin(url, tag["href"]))
        # Open Graph image
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            icon_candidates.append(urljoin(url, og_image["content"]))
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
                metadata["favicon_file"] = filename
                break

        # Fallback: DuckDuckGo favicon
        if not local_candidates:
            domain = parsed.netloc
            duckduckgo_icon = fetch_duckduckgo_favicon(domain)
            if duckduckgo_icon != DEFAULT_FAVICON:
                local_candidates.append(duckduckgo_icon)
                metadata["favicon_file"] = f"{domain.replace('.', '_')}_duckduckgo.ico"

        metadata["webicon"] = local_candidates[0] if local_candidates else DEFAULT_FAVICON
        metadata["icon_candidates"] = local_candidates

        if metadata["title"] or metadata["description"] or metadata["webicon"] != DEFAULT_FAVICON:
            logger.info(f"scrape_meta_style succeeded for {url}")
            return metadata
        return None
    except Exception as e:
        logger.error(f"scrape_meta_style failed for {url}: {e}")
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Scrape metadata and download favicon via Cloudscraper (style module).")
    parser.add_argument("url", help="The URL to scrape")
    parser.add_argument("output", help="Path to JSON output file")
    args = parser.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    os.makedirs(out_dir, exist_ok=True)

    scraper = cloudscraper.create_scraper()
    try:
        html = fetch_html(args.url, scraper)
        meta = extract_metadata(html)
        meta["url"] = args.url
        # Favicon logic: download to output dir, not static/icons
        favicon_file = None
        if meta.get("favicon"):
            favicon_url = urljoin(args.url, meta["favicon"])
            try:
                resp = scraper.get(favicon_url, stream=True)
                resp.raise_for_status()
                filename = os.path.basename(favicon_url.split("?", 1)[0]) or "favicon.ico"
                filepath = os.path.join(out_dir, filename)
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                favicon_file = filename
            except Exception as e:
                print(f"Failed to download favicon from {favicon_url}: {e}", file=sys.stderr)
        if favicon_file:
            meta["favicon_file"] = favicon_file
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"Metadata and favicon saved to {out_dir}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
