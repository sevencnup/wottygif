# WottyGIF Media Generation

## Goal

Turn pasted, dropped, or selected image and video files into real GIF output that can be previewed and downloaded from the browser.

## Processing Flow

1. Vue keeps the browser `File` objects while showing local previews.
2. The client submits `multipart/form-data` to `POST /api/media/jobs`.
3. FastAPI validates mode, file count, MIME type, quality, and the 200 MB per-file limit.
4. Uploads are written to an isolated temporary directory.
5. Pillow generates image GIFs; FFmpeg generates video GIFs.
6. The result is stored in `backend/data/results/{job_id}.gif`.
7. The response moves from `processing` to `completed` or `failed` and includes result or error fields.
8. Vue displays the finished animation and links to `GET /api/media/jobs/{job_id}/result`.

## Mode Rules

| Mode | Input | Output |
| --- | --- | --- |
| `single_image` | Exactly one image | One GIF per submitted image |
| `multi_image` | Two to 24 images | One looping GIF, 700 ms per frame |
| `video` | Exactly one video | One GIF sampled from the full video |

The frontend submits multiple single images or videos as independent jobs. Multi-image mode submits all selected images in one job.

## Quality Presets

| Level | Maximum side | Palette colors | Video FPS |
| --- | ---: | ---: | ---: |
| 1 | 320 px | 64 | 6 |
| 2 | 480 px | 96 | 8 |
| 3 | 640 px | 128 | 10 |
| 4 | 960 px | 192 | 12 |
| 5 | 1280 px | 256 | 15 |

Image dimensions keep their aspect ratio. Multi-image frames are centered on a common white canvas. FFmpeg uses Lanczos scaling plus generated palette and palette-use filters.

## Runtime Requirements

- Python 3.10 or newer
- Pillow 11.2.1
- python-multipart 0.0.32
- FFmpeg available in `PATH`, or `WOTTYGIF_FFMPEG` set to its executable

Run both services from the repository root:

```powershell
pnpm dev
```

The generated result directory is intentionally excluded from Git. Jobs are currently held in memory, so their queue records reset when FastAPI restarts; generated files remain on disk until removed manually.

## Verification

Backend regression tests cover health, single-image generation, multi-image generation, result download, and invalid mode/file combinations:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Video generation is verified against a short FFmpeg-generated fixture because CI environments may not always include an FFmpeg executable.
