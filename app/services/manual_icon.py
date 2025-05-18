import os
from fastapi import UploadFile
from app.services.favicon_generator import ICON_DIR

def save_manual_icon(bookmark_id: int, file: UploadFile) -> str:
    """
    Save an uploaded icon file for a bookmark and return the static path.
    """
    # Safely handle file.filename being None by providing an empty string to splitext.
    # The existing `or ".png"` logic will then correctly default the extension.
    _name, _ext_val = os.path.splitext(file.filename if file.filename is not None else "")
    ext = _ext_val.lower() or ".png"

    filename = f"manual_{bookmark_id}{ext}"
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ICON_DIR / filename
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read()) # file.file is a SpooledTemporaryFile
    finally:
        file.file.close() # Ensure the spooled temporary file is closed
    return f"/static/icons/{filename}"
