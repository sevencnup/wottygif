# WottyGIF Backend

Python FastAPI backend for media processing workflows.

Supported Python version: 3.10 or newer.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

From the repository root you can also start backend and frontend together:

```powershell
pnpm dev
```

The unified launcher waits for `GET /api/health` before starting Vite and prints the backend error log if startup fails.

## Endpoints

Health check:

```text
GET http://127.0.0.1:8000/api/health
```

Create job:

```text
POST http://127.0.0.1:8000/api/media/jobs
```

Payload fields:

- `mode`: `single_image`, `multi_image`, `video`
- `quality`: `1` to `5`
- `assets`: media metadata list
