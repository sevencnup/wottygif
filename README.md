# WottyGIF

WottyGIF is being rebuilt as a Python backend plus Vue frontend media studio.

## Current Scope

- Paste-to-preview intake area for image assets
- Quality control from `1` to `5`
- Three production modes:
  - `single_image`: batch-generate one result per image
  - `multi_image`: combine multiple images into one result
  - `video`: send video assets into the video creation queue
- In-memory job queue for frontend and backend workflow verification

## Stack

- Backend: FastAPI
- Frontend: Vue 3 + Vite

## Development

Start backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Start frontend from the workspace root:

```powershell
cd F:\1python\xiangmu
pnpm --filter wottygif-frontend dev
```

## API Notes

`POST /api/media/jobs` now accepts:

- `mode`: `single_image` | `multi_image` | `video`
- `quality`: integer `1` to `5`
- `assets`: a list of asset metadata objects

## Version

Current version: `0.2.4`

## One Command Dev Start

After the backend virtual environment is ready, start both services from the repo root:

```powershell
pnpm dev
```

This launches:

- FastAPI at `http://127.0.0.1:8000`
- Vite frontend at `http://127.0.0.1:5173`

The launcher prefers `backend\.venv\Scripts\python.exe`. If that virtual environment is missing, it falls back to the system `python` command and then `py`. Python 3.10 or newer is supported.

The frontend starts only after the backend health check passes. If FastAPI cannot start, the launcher prints `backend-dev.err.log` in the terminal.
