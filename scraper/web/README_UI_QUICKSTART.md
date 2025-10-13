# Web UI Quickstart (Local)

This project ships a minimal static UI (`scraper/web/index.html`) that works with the local FastAPI backend.

Requirements:
- Python 3.11+
- A virtual environment with the project installed: `pip install -e .`
- Adzuna API credentials in your env: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`

Steps (PowerShell):
1. Start the backend API:
```
.\.venv\Scripts\python.exe -m uvicorn scraper.web.server:app --reload --port 8000
```
2. Open the UI:
- Double-click `scraper/web/index.html` (file://) or open in your browser.
3. Use the form:
- Upload a resume (PDF/DOC/DOCX), fill Job title, Location, Distance.
- Click "Search and Prepare CSV" and wait for the token.
- Click "Download CSV".

Notes:
- The UI first tries the async jobs API (`/api/jobs`); if unavailable, it falls back to the legacy `/api/prepare` path.
- Health/metrics and recommendations panels are optional enhancements and may be empty until data exists.
- CORS is configured to allow file:// origins and localhost.
