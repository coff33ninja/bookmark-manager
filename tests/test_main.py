from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert "Bookmarks Manager" in response.text

def test_create_bookmark():
    response = client.post("/bookmarks/", json={
        "url": "https://example.com",
        "title": "Example",
        "description": "This is an example bookmark.",
        "icon": "https://example.com/icon.png"
    })
    assert response.status_code == 201
    assert response.json()["title"] == "Example"

def test_get_bookmarks():
    response = client.get("/bookmarks/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_update_bookmark():
    response = client.put("/bookmarks/1", json={
        "title": "Updated Example"
    })
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Example"

def test_delete_bookmark():
    response = client.delete("/bookmarks/1")
    assert response.status_code == 204
    response = client.get("/bookmarks/1")
    assert response.status_code == 404