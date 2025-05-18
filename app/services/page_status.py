import requests
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# A common user agent can prevent some servers from blocking the request
# or returning different content.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/97.0.4692.99 Safari/537.36 BookmarksAppChecker/1.0"
)


def is_page_online(url_str: str, timeout: int = 7) -> bool:
    """
    Check if a URL is online, handling IPs with ports and trying both HTTP/HTTPS.
    Prioritizes HTTP if no scheme, then tries HTTPS if HTTP fails.
    If a scheme is provided, it's tried first.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    processed_url = url_str

    try:
        # Ensure URL has a scheme for the first attempt. Default to HTTP.
        parsed_initial = urlparse(processed_url)
        if not parsed_initial.scheme:
            # If no scheme, default to http for the first try.
            # This handles "example.com" and "example.com:8080" correctly.
            processed_url = f"http://{url_str}"
        elif parsed_initial.scheme not in ("http", "https"):
            logger.warning(f"URL {url_str} has an unsupported scheme '{parsed_initial.scheme}'. Will not check.")
            return False

        # First attempt (either original scheme if http/https, or http if no scheme)
        try:
            logger.debug(f"Attempting (1) to connect to {processed_url}")
            resp = requests.get(processed_url, timeout=timeout, allow_redirects=True, headers=headers)
            if resp.ok: # Status code < 400
                logger.info(f"Successfully connected to {processed_url} with status {resp.status_code}")
                return True
            logger.warning(f"Connection to {processed_url} resulted in status {resp.status_code}")
        except requests.exceptions.SSLError as e:
            logger.warning(f"SSL error for {processed_url}: {e}. Will try alternative.")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error for {processed_url}: {e}. Will try alternative.")
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout connecting to {processed_url}. Will try alternative.")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request exception for {processed_url}: {e}. Will try alternative.")

        # Second attempt (alternative scheme)
        alternative_url = None
        if processed_url.startswith("http://"):
            alternative_url = processed_url.replace("http://", "https://", 1)
        elif processed_url.startswith("https://"): # Should only happen if original URL was https and it failed
            alternative_url = processed_url.replace("https://", "http://", 1)

        if alternative_url:
            try:
                logger.debug(f"Attempting (2) to connect to {alternative_url}")
                resp = requests.get(alternative_url, timeout=timeout, allow_redirects=True, headers=headers)
                if resp.ok:
                    logger.info(f"Successfully connected to {alternative_url} with status {resp.status_code}")
                    return True
                logger.warning(f"Connection to {alternative_url} resulted in status {resp.status_code}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed for {alternative_url}: {e}")

        logger.info(f"All attempts to check {url_str} failed.")
        return False
    except Exception as e:
        # Catch any truly unexpected errors during URL processing or other logic.
        logger.error(f"Unexpected error checking online status for {url_str}: {e}")
        return False
