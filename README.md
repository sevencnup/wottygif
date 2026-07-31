# WottyGIF

WottyGIF is a local Python and Vue media studio that generates downloadable GIF files.

## Current Scope

- Paste-to-preview intake area for image assets
- Quality control from `1` to `5`
- Three production modes:
  - `single_image`: batch-generate one result per image
  - `multi_image`: combine multiple images into one result
  - `video`: convert video assets into GIF files
- Real GIF generation with result preview and download
- Compact responsive workspace tuned for desktop and mobile use

## Stack

- Backend: FastAPI
- Image processing: Pillow
- Video processing: FFmpeg
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

`POST /api/media/jobs` accepts `multipart/form-data`:

- `mode`: `single_image` | `multi_image` | `video`
- `quality`: integer `1` to `5`
- `origins`: one value per file (`paste` or `upload`)
- `files`: the real image or video files

Completed jobs expose `GET /api/media/jobs/{job_id}/result` for GIF preview and download. Generated files are stored under `backend/data/results` and are ignored by Git.

## Version

Current version: `0.3.0`

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
