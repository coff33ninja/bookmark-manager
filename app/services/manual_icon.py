import os
from pathlib import Path
from fastapi import UploadFile
from app.services.favicon_generator import ICON_DIR

def save_manual_icon(bookmark_id: int, file: UploadFile) -> str:
    """
    Save an uploaded icon file for a bookmark and return the static path.
    """
    ext = os.path.splitext(file.filename)[1].lower() or ".png"
    filename = f"manual_{bookmark_id}{ext}"
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ICON_DIR / filename
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    return f"/static/icons/{filename}"
