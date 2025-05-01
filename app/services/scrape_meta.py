#!/usr/bin/env python3
"""
scrape_meta.py

Usage:
    python scrape_meta.py <URL> <output.json>

Installs:
    pip install cloudscraper beautifulsoup4
"""

import argparse  # CLI parsing :contentReference[oaicite:8]{index=8}
import json
import os
import sys
from urllib.parse import (
    urljoin,
)  # resolve relative URLs :contentReference[oaicite:9]{index=9}

import cloudscraper  # bypass Cloudflare IUAM :contentReference[oaicite:10]{index=10}
from bs4 import BeautifulSoup  # HTML parsing :contentReference[oaicite:11]{index=11}


def fetch_html(url, scraper, timeout=15):
    """Fetch page HTML using Cloudscraper."""
    resp = scraper.get(url, timeout=timeout)
    resp.raise_for_status()  # HTTPError if not 2xx :contentReference[oaicite:12]{index=12}
    return resp.text


def extract_metadata(html):
    """Extract common metadata into a dict."""
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
        data["title"] = title_tag.string.strip()

    if desc := soup.find("meta", attrs={"name": "description"}):
        data["description"] = desc.get("content", "").strip()

    for prop in ("og:title", "og:site_name", "og:description"):
        if tag := soup.find("meta", property=prop):
            data[prop] = tag.get("content", "").strip()

    if icon := soup.find("link", rel=lambda x: x and "icon" in x.lower()):
        data["favicon"] = icon.get("href")

    return data


def download_favicon(favicon_url, base_url, scraper, save_dir):
    """
    Resolve and download the favicon image.
    Returns the local filename or None on failure.
    """
    abs_url = urljoin(
        base_url, favicon_url
    )  # make absolute URL :contentReference[oaicite:13]{index=13}
    try:
        resp = scraper.get(abs_url, stream=True)
        resp.raise_for_status()
        filename = os.path.basename(abs_url.split("?", 1)[0]) or "favicon.ico"
        filepath = os.path.join(save_dir, filename)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return filename
    except Exception as e:
        print(f"Failed to download favicon from {abs_url}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape metadata and download favicon via Cloudscraper."
    )
    parser.add_argument("url", help="The URL to scrape")
    parser.add_argument("output", help="Path to JSON output file")
    args = parser.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    os.makedirs(out_dir, exist_ok=True)

    scraper = (
        cloudscraper.create_scraper()
    )  # drop-in replacement for requests.Session :contentReference[oaicite:14]{index=14}

    try:
        html = fetch_html(args.url, scraper)
        meta = extract_metadata(html)
        meta["url"] = args.url

        if meta.get("favicon"):
            fname = download_favicon(meta["favicon"], args.url, scraper, out_dir)
            if fname:
                meta["favicon_file"] = fname

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"Metadata and favicon saved to {out_dir}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
