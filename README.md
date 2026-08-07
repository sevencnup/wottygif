# WottyGIF

WottyGIF is a local Python and Vue media studio that generates downloadable GIF files.

## Current Scope

- Paste-to-preview intake area for image assets
- Quality control from `1` to `5`
- Three production modes:
  - `single_image`: batch-generate one result per image
  - `multi_image`: combine multiple images into one result
  - `video`: trim a video segment up to 30 seconds and optionally crop the frame before GIF conversion
- Real GIF generation with result preview and download
- One-click ZIP download for all completed GIF results
- Three-column desktop editor and an app-style multi-screen mobile flow
- Interactive video frame cropping with drag, edge/corner resize, and precise percentage controls
- Video preview playback and direct segment start/end controls on desktop and mobile preview screens
- Mobile asset previews with file selection, removal, ordering, and a confirmed video-crop workflow
- Guided per-image cropping for single and multi-image modes with confirm, skip, previous, and recrop steps
- Confirmed image and video crops reflected consistently in source and production previews
- Solid-blue interface theme with a 110% large-screen workspace and unchanged mobile sizing
- Mode-scoped asset retention and direct image cropping inside the existing preview window
- Persistent completed-job history that is restored after backend restarts
- Anonymous browser-device isolation for completed lists, previews, and downloads
- Two-tab mobile bottom navigation using official Lucide icon components
- Mobile history integration for in-app system swipe-back navigation

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
- `clip_start_seconds`, `clip_end_seconds`: optional video trim range in seconds
- `crop_left_percent`, `crop_top_percent`, `crop_width_percent`, `crop_height_percent`: optional video crop box percentages
- `image_crop_options`: optional ordered JSON array of per-image crop boxes or `{ "skip": true }`
- `files`: the real image or video files

The frontend stores a random anonymous device ID in browser local storage and sends it as `X-WottyGIF-Device-ID`. Job lists are filtered by this header. Result and batch-download URLs carry the same ID as the `device_id` query parameter because image and download elements cannot attach custom request headers. This separates normal browser devices but is not a replacement for account authentication on an untrusted public network.

Completed jobs expose `GET /api/media/jobs/{job_id}/result` for GIF preview and download. Generated files and persistent job metadata are stored under `backend/data/results` and are ignored by Git. Existing GIF files without metadata are recovered as historical completed jobs when the backend starts.

## Version

Completed GIF files are temporary backend cache entries. They are automatically removed one hour after generation completes, along with their completed-task records.

Current version: `0.3.28`

## One Command Dev Start

After the backend virtual environment is ready, start both services from the repo root:

```powershell
pnpm dev
```

This launches:

- FastAPI at `http://127.0.0.1:8000`
- Vite frontend at `http://127.0.0.1:5173` and `http://<LAN-IP>:5173`

The launcher prefers `backend\.venv\Scripts\python.exe`. If that virtual environment is missing, it falls back to the system `python` command and then `py`. Python 3.10 or newer is supported.

The frontend starts only after the backend health check passes. If FastAPI cannot start, the launcher prints `backend-dev.err.log` in the terminal. Use the printed LAN URL from another device on the same network.
