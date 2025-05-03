import pytest
from unittest.mock import patch, MagicMock
from app.services import network_detector, favicon_generator

def test_is_ip_url():
    assert network_detector.is_ip_url("http://192.168.1.1") is True
    assert network_detector.is_ip_url("http://example.com") is False

def test_get_network_tag():
    assert network_detector.get_network_tag("http://192.168.1.1") == "local-server"
    assert network_detector.get_network_tag("http://8.8.8.8") == "remote-server"

@patch("app.services.favicon_generator.download_icon")
def test_generate_favicon(mock_download_icon):
    mock_download_icon.return_value = "/static/icons/example.ico"
    icon_path = favicon_generator.generate_favicon("http://example.com")
    assert icon_path == "/static/icons/example.ico"
