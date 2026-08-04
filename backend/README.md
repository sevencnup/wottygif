# WottyGIF Backend

Python FastAPI backend for real image and video to GIF generation.

Supported Python version: 3.10 or newer.

Image conversion uses Pillow. Video conversion requires FFmpeg in `PATH`, or an explicit executable path in `WOTTYGIF_FFMPEG`.

Completed job metadata is persisted in `data/results/jobs.json`. On startup, the API restores saved jobs and imports any existing `.gif` without metadata as a historical completed result.

Generated GIF files are retained for one hour from each job's `completed_at` time. The API removes the GIF file and its completed-job metadata together. Cleanup runs at startup, every 60 seconds while the backend is running, and before result-list or download requests.

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
- `clip_start_seconds`, `clip_end_seconds`: optional video trim range in seconds
- `crop_left_percent`, `crop_top_percent`, `crop_width_percent`, `crop_height_percent`: optional video crop box percentages
- `image_crop_options`: optional JSON array ordered to match `files`; each entry contains image crop percentages or `{ "skip": true }`
- `files`: repeated image or video uploads

Video mode can trim a source video down to a selected segment. The selected segment must not exceed 30 seconds.

Only confirmed client crop values are submitted. The frontend mirrors those confirmed image and video crop boxes in its source and production previews before the same percentages are applied during backend encoding.

Download a completed result:

```text
GET http://127.0.0.1:8000/api/media/jobs/{job_id}/result
```

Download all currently completed results as a ZIP archive:

```text
GET http://127.0.0.1:8000/api/media/jobs/batch-download
```
