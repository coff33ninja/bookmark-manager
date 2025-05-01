import requests

def is_page_online(url: str, timeout: int = 7) -> bool:
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False
