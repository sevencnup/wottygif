# WottyGIF Backend

Python FastAPI backend for real image and video to GIF generation.

Supported Python version: 3.10 or newer.

Image conversion uses Pillow. Video conversion requires FFmpeg in `PATH`, or an explicit executable path in `WOTTYGIF_FFMPEG`.

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

Multipart fields:

- `mode`: `single_image`, `multi_image`, `video`
- `quality`: `1` to `5`
- `origins`: repeated `paste` or `upload` values
- `files`: repeated image or video uploads

Download a completed result:

```text
GET http://127.0.0.1:8000/api/media/jobs/{job_id}/result
```
