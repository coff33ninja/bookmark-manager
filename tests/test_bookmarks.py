import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def create_bookmark():
    response = client.post(
        "/bookmarks",
        json={
            "url": "https://example.com",
            "title": "Example",
            "description": "An example bookmark",
            "webicon": "https://example.com/icon.png",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_bookmark():
    response = client.post(
        "/bookmarks",
        json={
            "url": "https://example.com",
            "title": "Example",
            "description": "An example bookmark",
            "webicon": "https://example.com/icon.png",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Example"
    assert data["url"] == "https://example.com"


def test_get_bookmark(create_bookmark):
    bookmark_id = create_bookmark["id"]
    response = client.get(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == bookmark_id
    assert data["title"] == "Example"


def test_update_bookmark(create_bookmark):
    bookmark_id = create_bookmark["id"]
    response = client.patch(
        f"/bookmarks/{bookmark_id}", json={"title": "Updated Example"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Example"


def test_delete_bookmark(create_bookmark):
    bookmark_id = create_bookmark["id"]
    response = client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code in (200, 204)
    # Confirm deletion
    response = client.get(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 404


def test_get_all_bookmarks():
    response = client.get("/bookmarks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
