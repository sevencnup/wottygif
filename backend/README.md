# WottyGIF Backend

Python FastAPI backend for media processing workflows.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Health check:

```text
GET http://127.0.0.1:8000/api/health
```
