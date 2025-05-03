import requests
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


def is_page_online(url: str, timeout: int = 7) -> bool:
    """
    Check if a URL is online, handling IPs with ports and trying both HTTP/HTTPS.
    """
    try:
        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            parsed = urlparse(f"http://{url}")
            if parsed.port or ":" in parsed.netloc:
                url = f"http://{parsed.netloc}"
            else:
                url = f"http://{url}"

        # Try HTTP first
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return True
        except requests.exceptions.SSLError:
            logger.warning(f"SSL error for {url}, trying HTTPS")
        except requests.exceptions.ConnectionError:
            logger.info(f"Connection failed for {url}")
            pass

        # Try HTTPS if HTTP fails
        if url.startswith("http://"):
            https_url = url.replace("http://", "https://")
            try:
                resp = requests.get(https_url, timeout=timeout, allow_redirects=True)
                if resp.status_code == 200:
                    return True
            except requests.exceptions.RequestException as e:
                logger.error(f"HTTPS request failed for {https_url}: {str(e)}")
                pass

        return False
    except Exception as e:
        logger.error(f"Error checking {url}: {str(e)}")
        return False
