import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock

client = TestClient(app)

@patch("app.routes.bookmarks.fetch_metadata_combined")
def test_add_bookmark(mock_fetch_metadata):
    mock_fetch_metadata.return_value = {
        "webicon": "/static/favicon.ico",
        "icon_candidates": ["/static/favicon.ico"],
    }
    response = client.post("/bookmarks", json={"url": "http://example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://example.com"
    assert "id" in data

def test_get_bookmarks():
    response = client.get("/bookmarks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@patch("app.routes.bookmarks.fetch_metadata_combined")
def test_get_metadata(mock_fetch_metadata):
    mock_fetch_metadata.return_value = {
        "title": "Test Title",
        "description": "Test Description",
        "webicon": "/static/favicon.ico",
        "icon_candidates": ["/static/favicon.ico"],
        "extra_metadata": {},
    }
    response = client.post("/fetch-metadata", json={"url": "http://example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Title"
    assert data["webicon"] == "/static/favicon.ico"

def test_search_bookmarks():
    response = client.get("/search", params={"query": "example"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
