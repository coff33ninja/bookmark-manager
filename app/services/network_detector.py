import ipaddress
# import re # No longer needed
from urllib.parse import urlparse
from typing import Tuple, Optional
from .page_status import is_page_online
import logging
import socket # Added for DNS resolution

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

    # __init__ removed as ip_regex is no longer used

    def is_ip_url(self, url: str) -> bool:
        """Check if the URL's hostname is a valid IP address (IPv4 or IPv6)."""
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        try:
            ipaddress.ip_address(host)  # This handles both IPv4 and IPv6
            return True
        except ValueError:
            # Not a valid IP string
            return False

    def _get_ipv4_address_from_host(self, host: str, original_url: str) -> Tuple[Optional[ipaddress.IPv4Address], Optional[str]]:
        """
        Tries to get an IPv4Address object from a host string.
        Handles direct IP parsing and DNS resolution.
        Returns (IPv4Address object or None, classification_if_error_or_ipv6 or None)
        """
        try:
            # socket.gethostbyname resolves hostnames to IPv4 or returns IPv4 if 'host' is already one.
            # It raises socket.gaierror if resolution fails.
            # It can also raise UnicodeError for too long/invalid hostnames.
            resolved_ip_str = socket.gethostbyname(host)

            # Now parse the resolved IP string. It should be IPv4.
            try:
                ipv4_address = ipaddress.IPv4Address(resolved_ip_str)
                return ipv4_address, None
            except ipaddress.AddressValueError:
                # This would be unusual if gethostbyname returned something not parsable as IPv4.
                # Could happen if host was an IPv6 address and gethostbyname returned it (platform-dependent).
                logger.warning(f"Host '{host}' (resolved to '{resolved_ip_str}') is not a valid IPv4 address. URL: {original_url}")
                try: # Check if it's an IPv6 address
                    if isinstance(ipaddress.ip_address(resolved_ip_str), ipaddress.IPv6Address):
                         logger.warning(f"Host '{host}' (resolved to '{resolved_ip_str}') is IPv6. URL: {original_url}")
                         return None, "IPv6 Host"
                except ValueError:
                    pass # Not IPv6 either
                return None, "Invalid Resolved IP"

        except socket.gaierror:
            # This can mean DNS resolution failed, or host is an IPv6 address string (gethostbyname might fail for IPv6 hosts).
            # Try to parse host directly as an IP to check if it's IPv6.
            try:
                potential_ip = ipaddress.ip_address(host)
                if isinstance(potential_ip, ipaddress.IPv6Address):
                    logger.warning(f"Host '{host}' is an IPv6 address (gaierror on gethostbyname). URL: {original_url}")
                    return None, "IPv6 Host"
            except ValueError:
                # Not a direct IP string, and resolution failed.
                pass # Continue to log as unresolvable
            logger.error(f"DNS resolution failed for host: {host} in URL: {original_url}")
            return None, "Unresolvable Host"
        except UnicodeEncodeError: # For hostnames that are too long or contain invalid characters for DNS
             logger.error(f"Hostname '{host}' is too long or contains invalid characters for DNS resolution. URL: {original_url}")
             return None, "Invalid Hostname"
        except Exception as e: # Catch any other unexpected errors during resolution/parsing
            logger.error(f"Unexpected error getting IPv4 for host '{host}': {e}. URL: {original_url}")
            return None, "Host Processing Error"

    def classify_url(self, url: str) -> Tuple[str, bool]:
        """
        Classify a URL as Local, Remote, VPN, etc., and check its accessibility.
        Handles both IP addresses and hostnames (which will be resolved).
        Returns: (classification_string, is_accessible_bool)
        """
        normalized_url = url
        if not normalized_url.startswith(("http://", "https://")):
            normalized_url = f"http://{normalized_url}"

        parsed = urlparse(normalized_url)
        host = parsed.hostname

        if not host:
            logger.warning(f"Could not parse hostname from URL: {url}")
            return "Invalid URL Structure", False

        ipv4_obj, pre_classification = self._get_ipv4_address_from_host(host, url)

        if pre_classification:
            # For these cases (e.g., IPv6, Unresolvable), check accessibility if relevant.
            if pre_classification in ["Unresolvable Host", "Invalid Hostname", "Host Processing Error"]:
                return pre_classification, False # Cannot be online

            is_accessible_early = is_page_online(normalized_url)
            return pre_classification, is_accessible_early

        if not ipv4_obj: # Should not happen if _get_ipv4_address_from_host is correct
             logger.critical(f"Internal logic error: ipv4_obj is None without pre_classification for host {host}, URL {url}")
             is_accessible_fallback = is_page_online(normalized_url)
             return "Internal Processing Error", is_accessible_fallback

        # Now we have an ipv4_obj, proceed with classification and accessibility check
        is_accessible = is_page_online(normalized_url)

        for private_range in self.PRIVATE_IP_RANGES:
            if ipv4_obj in private_range:
                return "Local" if is_accessible else "Local (Offline)", is_accessible

        for vpn_range in self.VPN_IP_RANGES:
            if ipv4_obj in vpn_range:
                return "VPN", is_accessible

        return "Remote", is_accessible

    def get_network_tag(self, url: str) -> str:
        """Return a tag for the URL's network type (e.g., 'local-server')."""
        classification, _ = self.classify_url(url)
        # Updated map for new/changed classification strings
        tag_map = {
            "Local": "local-server",
            "Local (Offline)": "local-server-offline",
            "VPN": "vpn-server",
            "Remote": "remote-server",
            "IPv6 Host": "ipv6-server",
            "Unresolvable Host": "unresolvable-server",
            "Invalid URL Structure": "invalid-url-structure",
            "Invalid Resolved IP": "invalid-resolved-ip",
            "Invalid Hostname": "invalid-hostname",
            "Host Processing Error": "host-processing-error",
            "Internal Processing Error": "internal-processing-error",
        }
        return tag_map.get(classification, "unknown-classification-tag")
