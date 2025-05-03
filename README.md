# Bookmarks Manager

A simple and efficient bookmarks manager built with FastAPI/Flask that allows users to save, manage, and sync their bookmarks. The application fetches metadata from the saved links, including icons and page descriptions, providing a user-friendly interface with dark mode support.

## Features

- Save bookmarks with URL, title, description, and icon.
- Fetch and display metadata from the saved links.
- Dark mode design for a modern look and feel.
- Clickable bookmarks that redirect to the original pages.
- RESTful API for managing bookmarks with endpoints to:
  - Add new bookmarks
  - Retrieve all bookmarks
  - Update bookmark details and icons
  - Delete bookmarks with icon recycling
  - Search bookmarks by title, description, or URL
  - Cluster bookmarks based on content similarity
  - Suggest tags for bookmarks based on content analysis

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

## API Endpoints

- `POST /bookmarks` - Add a new bookmark.
- `GET /bookmarks` - Retrieve all bookmarks.
- `PATCH /bookmarks/{bookmark_id}` - Update bookmark details.
- `PATCH /bookmarks/{bookmark_id}/webicon` - Update the webicon of a bookmark.
- `DELETE /bookmarks/{bookmark_id}` - Delete a bookmark and recycle its icons.
- `POST /fetch-metadata` - Fetch metadata for a given URL.
- `GET /search?query=your_query` - Search bookmarks by title, description, or URL.
- `GET /cluster-bookmarks` - Cluster bookmarks based on content similarity.
- `POST /suggest-tags` - Suggest tags for a bookmark based on its content.

## Project Structure
```
.gitignore
README.md
requirements.txt
bookmarks.db
app/
|-- main.py
|-- models.py
|-- routes/
|   `-- bookmarks.py
|-- services/
|   |-- favicon_generator.py
|   |-- metadata_fetcher.py
|   |-- page_status.py
|-- static/
|   |-- favicon.ico
|   |-- favicon.svg
|   |-- css/
|   |   `-- dark_mode.css
|   |-- js/
templates/
`-- drivers/
    `-- geckodriver.exe
tests/
|-- test_bookmarks.py
`-- test_main.py
```
`-- test_main.py

## Testing

- Tests are located in the `tests/` directory.
- Run tests using your preferred test runner, for example:
  ```
  pytest tests/
  ```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
