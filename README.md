# Bookmarks Manager

A simple and efficient bookmarks manager built with FastAPI/Flask that allows users to save, manage, and sync their bookmarks. The application fetches metadata from the saved links, including icons and page descriptions, providing a user-friendly interface with dark mode support.

## Features

- Save bookmarks with URL, title, description, and icon.
- Fetch and display metadata from the saved links.
- Dark mode design for a modern look and feel.
- Clickable bookmarks that redirect to the original pages.
- RESTful API for managing bookmarks.

## Project Structure
```
bookmark-manager/
|-- app/
|   |-- routes/
|   |   `-- bookmarks.py
|   |-- services/
|   |   |-- cloudscraper_meta.py
|   |   |-- favicon_generator.py
|   |   |-- geckodriver_setup.py
|   |   |-- metadata_fetcher.py
|   |   |-- scrape_meta.py
|   |   |-- scrape_meta_method.py
|   |   |-- scrape_meta_style.py
|   |   `-- selenium_meta.py
|   |-- templates/
|   |   `-- index.html
|   |-- static/
|   |   |-- css/
|   |   |   `-- dark_mode.css
|   |   |-- icons/
|   |   |   |-- chatgpt_com_favicon.ico
|   |   |   |-- chatgpt_comfavicon.ico
|   |   |   |-- fmhy_net_favicon.ico
|   |   |   |-- grok_com_favicon.png
|   |   |   |-- paimon_moe_favicon.ico
|   |   |   |-- theresanaiforthat_com_apple-touch-icon.png
|   |   |   |-- theresanaiforthat_com_favicon.ico
|   |   |   `-- www_riffusion_com_apple-touch-icon.png
|   |   |-- favicon.ico
|   |   |-- favicon.svg
|   |   `-- js/
|-- drivers/
|   `-- geckodriver.exe
|-- tests/
|   |-- test_bookmarks.py
|   `-- test_main.py
|-- app/
|   |-- main.py
|   `-- models.py
|-- README.md
|-- requirements.txt
`-- bookmarks.db
```
## Installation

1. Clone the repository:
   ```
   git clone https://github.com/coff33ninja/bookmarks-manager.git
   cd bookmarks-manager
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application using uvicorn (recommended for development with auto-reload):
   ```
   uvicorn app.main:app --reload
   ```
4. Alternatively, you can run the app directly with Python:
   ```
   python -m app.main
   ```
5. If you are using Flask, run the app with:
   ```
   python -m flask run
   ```
6. If you are using FastAPI, run the app with:
   ```
   python -m fastapi
   ```
7. If you are using Flask with Gunicorn, run the app with:
   ```
   gunicorn -w 4 -k gthread -b
   ```

## Usage

- Open your browser and navigate to `http://localhost:8000/website` (or the appropriate port).
- Use the interface to add, view, update, or delete bookmarks.
- Enjoy the dark mode experience while managing your bookmarks!

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
