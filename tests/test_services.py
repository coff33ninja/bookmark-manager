import pytest
from unittest.mock import patch, MagicMock
from app.services.metadata_fetcher import (
    fetch_metadata_combined,
    fetch_metadata_scrape_meta,
    fetch_metadata_cloudscraper,
    fetch_metadata_with_selenium,
)

@patch("app.services.metadata_fetcher.cloudscraper.create_scraper")
def test_fetch_metadata_scrape_meta(mock_create_scraper):
    mock_scraper = MagicMock()
    mock_scraper.get.return_value.text = """
    <html><head><title>Test Title</title><meta name="description" content="Test Description"></head><body></body></html>
    """
    mock_create_scraper.return_value = mock_scraper

    result = fetch_metadata_scrape_meta("http://example.com")
    assert "title" in result
    assert result["title"] == "Test Title"
    assert "description" in result
    assert result["description"] == "Test Description"

@patch("app.services.metadata_fetcher.cloudscraper.create_scraper")
def test_fetch_metadata_cloudscraper(mock_create_scraper):
    mock_scraper = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<html><head><title>Cloudscraper Title</title><meta name='description' content='Cloudscraper Description'></head><body></body></html>"
    mock_response.encoding = "utf-8"
    mock_scraper.get.return_value = mock_response
    mock_create_scraper.return_value = mock_scraper

    result = fetch_metadata_cloudscraper("http://example.com")
    assert "title" in result
    assert result["title"] == "Cloudscraper Title"
    assert "description" in result
    assert result["description"] == "Cloudscraper Description"

@patch("app.services.metadata_fetcher.setup_geckodriver")
@patch("app.services.metadata_fetcher.webdriver.Firefox")
def test_fetch_metadata_with_selenium(mock_firefox, mock_setup_geckodriver):
    mock_driver = MagicMock()
    mock_driver.page_source = """
    <html><head><title>Selenium Title</title><meta name="description" content="Selenium Description"></head><body></body></html>
    """
    mock_firefox.return_value.__enter__.return_value = mock_driver
    mock_setup_geckodriver.return_value = "/path/to/geckodriver"

    result = fetch_metadata_with_selenium("http://example.com")
    assert "title" in result
    assert result["title"] == "Selenium Title"
    assert "description" in result
    assert result["description"] == "Selenium Description"

def test_fetch_metadata_combined(monkeypatch):
    def mock_fetch_metadata_scrape_meta(url):
        return {"title": "Scrape Meta Title", "description": "Scrape Meta Description", "webicon": "/static/favicon.ico", "icon_candidates": []}

    monkeypatch.setattr("app.services.metadata_fetcher.fetch_metadata_scrape_meta", mock_fetch_metadata_scrape_meta)

    result = fetch_metadata_combined("http://example.com")
    assert "title" in result
    assert result["title"] == "Scrape Meta Title"
