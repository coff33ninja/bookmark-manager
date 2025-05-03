import ipaddress
import re
from urllib.parse import urlparse
from typing import Tuple
from .page_status import is_page_online
import logging

logger = logging.getLogger(__name__)

class NetworkDetector:
    # Private IP ranges
    PRIVATE_IP_RANGES = [
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
    ]

    # VPN IP ranges (e.g., Tailscale)
    VPN_IP_RANGES = [
        ipaddress.IPv4Network("100.64.0.0/10"),  # Tailscale
        # Add other VPN ranges as needed (e.g., WireGuard, OpenVPN)
    ]

    def __init__(self):
        self.ip_regex = re.compile(r"^(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3})(?::[0-9]+)?$")

    def is_ip_url(self, url: str) -> bool:
        """Check if the URL uses an IP address (with optional port)."""
        parsed = urlparse(url)
        host = parsed.hostname or parsed.netloc.split(":")[0] if parsed.netloc else ""
        return bool(self.ip_regex.match(host))

    def classify_url(self, url: str) -> Tuple[str, bool]:
        """
        Classify a URL as Local, Remote, VPN, or Local (Offline).
        Returns: (classification, is_accessible)
        """
        try:
            # Ensure URL has a scheme
            if not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            
            parsed = urlparse(url)
            host = parsed.hostname or parsed.netloc.split(":")[0]
            port = parsed.port
            ip_str = host

            # Validate IP
            try:
                ip = ipaddress.ip_address(ip_str)
                if not isinstance(ip, ipaddress.IPv4Address):
                    logger.warning(f"IPv6 not supported: {url}")
                    return "Unknown", False
            except ValueError:
                logger.error(f"Invalid IP address: {ip_str}")
                return "Invalid", False

            # Check accessibility
            is_accessible = is_page_online(url)
            logger.info(f"URL {url} with port {port} is {'accessible' if is_accessible else 'inaccessible'}")

            # Classify based on IP range
            for private_range in self.PRIVATE_IP_RANGES:
                if ip in private_range:
                    return "Local" if is_accessible else "Local (Offline)", is_accessible

            for vpn_range in self.VPN_IP_RANGES:
                if ip in vpn_range:
                    return "VPN", is_accessible

            # Default to Remote for public IPs
            return "Remote", is_accessible

        except Exception as e:
            logger.error(f"Error classifying URL {url}: {str(e)}")
            return "Unknown", False

    def get_network_tag(self, url: str) -> str:
        """Return a tag for the URL's network type (e.g., 'local-server')."""
        classification, _ = self.classify_url(url)
        tag_map = {
            "Local": "local-server",
            "Local (Offline)": "local-server-offline",
            "VPN": "vpn-server",
            "Remote": "remote-server",
            "Unknown": "unknown-server",
            "Invalid": "invalid-server"
        }
        return tag_map.get(classification, "unknown-server")