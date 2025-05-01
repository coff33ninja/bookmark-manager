import os
import requests
import zipfile

def setup_geckodriver():
    url = "https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-win32.zip"
    driver_dir = "drivers"
    driver_path = os.path.join(driver_dir, "geckodriver.exe")
    if not os.path.exists(driver_path):
        os.makedirs(driver_dir, exist_ok=True)
        response = requests.get(url, stream=True)
        zip_path = os.path.join(driver_dir, "geckodriver.zip")
        with open(zip_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=128):
                file.write(chunk)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(driver_dir)
        os.remove(zip_path)
    return driver_path
