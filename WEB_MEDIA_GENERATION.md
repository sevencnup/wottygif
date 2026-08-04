# WottyGIF Media Generation

> Backend retention: completed GIF cache files and their task records expire one hour after generation completes. Cleanup runs on backend startup, every 60 seconds, and when completed results are listed or downloaded.

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

Job metadata is atomically persisted to `backend/data/results/jobs.json` whenever a task starts, completes, fails, or is removed. Backend startup reloads that metadata, reconnects completed jobs to their GIF files, marks interrupted processing jobs as failed, and imports orphaned GIF files as historical completed results. The frontend refreshes the job list every two seconds and whenever the completed screen opens, so a running page recovers after a backend restart without a manual reload.

## Mode Rules

| Mode | Input | Output |
| --- | --- | --- |
| `single_image` | Exactly one image | One GIF per submitted image |
| `multi_image` | Two to 24 images | One looping GIF, 700 ms per frame |
| `video` | Exactly one video, with an optional trimmed segment up to 30 seconds | One GIF sampled from the selected segment |

The frontend submits multiple single images or videos as independent jobs. Multi-image mode submits all selected images in one job.

## Quality Presets

| Level | Maximum side | Palette colors | Video FPS |
| --- | ---: | ---: | ---: |
| 1 | 360 px | 128 | 6 |
| 2 | 540 px | 160 | 8 |
| 3 | 720 px | 192 | 10 |
| 4 | 1080 px | 224 | 12 |
| 5 | 1920 px | 256 | 15 |

Image dimensions keep their aspect ratio. Multi-image frames are centered on a common white canvas. Pillow uses Median Cut with quality-scaled K-Means refinement and no error-diffusion dithering. FFmpeg uses Lanczos scaling, a full-video palette, and no Sierra dithering. These settings reduce patterned texture and preserve more high-quality detail, while the GIF format still has a hard limit of 256 colors per palette.

Video mode can trim by start and end time before encoding. The selected segment must stay within the source duration and may not exceed 30 seconds. The desktop and mobile production preview screens expose the same start and end fields so timing can be adjusted immediately before generation. Video mode also provides an interactive crop canvas on desktop and mobile: the crop box can be moved, resized from every edge or corner, or adjusted with synchronized width, height, left, and top percentage controls before scaling and palette generation.

On mobile, all three modes expose the uploaded files in a scrollable asset workspace before generation. Users can inspect the selected source at its full aspect ratio, switch between files, remove files, reorder them, and add more. Video crop changes remain a draft until the user confirms them; unconfirmed crop changes block preview and generation so edits cannot be applied accidentally.

Single-image and multi-image modes can start a guided crop workflow. Starting the workflow marks every image as pending; the current image must be confirmed or explicitly skipped before another image can be selected. Confirm advances to the next image, while completed images remain available for previous-image navigation and recropping. Each confirmed percentage crop box is submitted in file order through `image_crop_options` and applied by Pillow before resizing, shared-canvas composition, palette generation, and GIF encoding.

The desktop production preview, mobile source preview, and mobile production preview all render from the confirmed crop box for the selected asset. Video previews include explicit play and pause controls after cropping without forcing autoplay. Draft edits remain inside the crop editor until confirmed, skipped images retain their full frame, and each multi-image asset restores its own crop when selected. Preview viewports preserve the exact post-crop aspect ratio, including narrow portrait and wide landscape selections.

Image crop manipulation is embedded directly in the existing desktop production preview and mobile source preview. Entering crop mode overlays the crop box and drag handles on that preview instead of creating a duplicate image canvas. Completing the final image closes the handles and restores the confirmed cropped result; the recrop command reopens the same preview surface with the saved crop box.

Mode changes keep separate in-memory image and video asset groups. Switching between single-image and multi-image modes keeps the active image list in place, while switching between an image mode and video mode parks the current group and restores the other group. Object URLs are released only when an asset is explicitly removed, its active group is cleared, or the app unmounts.

The interface uses a solid-blue accent system without decorative gradients. On large web viewports of at least 1365 by 640 CSS pixels, the complete desktop workspace renders at 110% scale while remaining constrained to the viewport. Tablet, narrow-window, and mobile layouts retain their existing scale and responsive navigation.

Mobile bottom navigation uses the `House`, `CircleCheckBig`, and `Settings` components from `@lucide/vue`. Navigation buttons retain a 48 CSS-pixel tap target but have transparent backgrounds and no visible borders; only icon and label color indicate the active destination.

The result stage can download all currently completed GIF files in one ZIP archive through `GET /api/media/jobs/batch-download`.

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

Backend regression tests cover health, palette quality, high-resolution preservation, single-image and multi-image generation, batch ZIP download, the 30-second video limit, result download, and invalid mode/file combinations:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Video generation is verified against a short FFmpeg-generated fixture because CI environments may not always include an FFmpeg executable.
