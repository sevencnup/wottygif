from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel


class ProcessingMode(str, Enum):
    single_image = "single_image"
    multi_image = "multi_image"
    video = "video"


class AssetKind(str, Enum):
    image = "image"
    video = "video"


class AssetOrigin(str, Enum):
    paste = "paste"
    upload = "upload"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MediaAsset(BaseModel):
    id: str
    name: str
    kind: AssetKind
    origin: AssetOrigin
    mime_type: str
    size_bytes: int


class MediaJob(BaseModel):
    id: str
    mode: ProcessingMode
    quality: int
    source_name: str
    asset_count: int
    assets: list[MediaAsset]
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None = None
    result_name: str | None = None
    result_url: str | None = None
    error_message: str | None = None


app = FastAPI(title="WottyGIF API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "data" / "results"
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_ASSETS = 24
QUALITY_SETTINGS = {
    1: {"max_side": 320, "colors": 64, "fps": 6},
    2: {"max_side": 480, "colors": 96, "fps": 8},
    3: {"max_side": 640, "colors": 128, "fps": 10},
    4: {"max_side": 960, "colors": 192, "fps": 12},
    5: {"max_side": 1280, "colors": 256, "fps": 15},
}

jobs: dict[str, MediaJob] = {}
result_paths: dict[str, Path] = {}


def asset_kind(upload: UploadFile) -> AssetKind:
    content_type = upload.content_type or ""
    if content_type.startswith("image/"):
        return AssetKind.image
    if content_type.startswith("video/"):
        return AssetKind.video
    raise HTTPException(status_code=422, detail=f"不支持的素材类型: {content_type or 'unknown'}")


def validate_uploads(mode: ProcessingMode, uploads: list[UploadFile]) -> list[AssetKind]:
    if not uploads:
        raise HTTPException(status_code=422, detail="请至少上传一个素材。")
    if len(uploads) > MAX_ASSETS:
        raise HTTPException(status_code=422, detail=f"一次最多上传 {MAX_ASSETS} 个素材。")

    kinds = [asset_kind(upload) for upload in uploads]
    if mode == ProcessingMode.single_image and (len(uploads) != 1 or kinds[0] != AssetKind.image):
        raise HTTPException(status_code=422, detail="单图模式每个任务只能上传一张图片。")
    if mode == ProcessingMode.multi_image and (len(uploads) < 2 or any(kind != AssetKind.image for kind in kinds)):
        raise HTTPException(status_code=422, detail="多图模式至少需要两张图片。")
    if mode == ProcessingMode.video and (len(uploads) != 1 or kinds[0] != AssetKind.video):
        raise HTTPException(status_code=422, detail="视频模式每个任务只能上传一个视频。")
    return kinds


def normalized_origins(origins: list[AssetOrigin], asset_count: int) -> list[AssetOrigin]:
    if len(origins) == 1:
        return origins * asset_count
    if len(origins) != asset_count:
        raise HTTPException(status_code=422, detail="素材来源数量与上传文件数量不一致。")
    return origins


async def save_upload(upload: UploadFile, destination: Path) -> int:
    total = 0
    with destination.open("wb") as target:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail=f"文件 {upload.filename} 超过 200 MB。")
            target.write(chunk)
    return total


def prepare_image(path: Path, max_side: int) -> Image.Image:
    try:
        with Image.open(path) as source:
            frame = ImageOps.exif_transpose(source).convert("RGB")
            frame.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            return frame.copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"无法读取图片 {path.name}") from exc


def generate_image_gif(input_paths: list[Path], output_path: Path, quality: int) -> None:
    settings = QUALITY_SETTINGS[quality]
    source_frames = [prepare_image(path, settings["max_side"]) for path in input_paths]
    target_width = max(frame.width for frame in source_frames)
    target_height = max(frame.height for frame in source_frames)
    frames: list[Image.Image] = []

    for source in source_frames:
        canvas = Image.new("RGB", (target_width, target_height), "white")
        offset = ((target_width - source.width) // 2, (target_height - source.height) // 2)
        canvas.paste(source, offset)
        frames.append(
            canvas.quantize(
                colors=settings["colors"],
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG,
            )
        )

    frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=700,
        loop=0,
        optimize=True,
        disposal=2,
    )


def find_ffmpeg() -> str:
    configured = os.environ.get("WOTTYGIF_FFMPEG")
    executable = configured or shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("未找到 FFmpeg，请安装后加入 PATH，或设置 WOTTYGIF_FFMPEG。")
    return executable


def generate_video_gif(input_path: Path, output_path: Path, quality: int) -> None:
    settings = QUALITY_SETTINGS[quality]
    video_filter = (
        f"fps={settings['fps']},scale='min({settings['max_side']},iw)':-2:flags=lanczos,"
        f"split[source][palette_input];[palette_input]palettegen=max_colors={settings['colors']}[palette];"
        "[source][palette]paletteuse=dither=sierra2_4a"
    )
    completed = subprocess.run(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            video_filter,
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0 or not output_path.exists():
        detail = completed.stderr.strip() or "FFmpeg 未生成输出文件。"
        raise RuntimeError(detail[-1200:])


def result_filename(mode: ProcessingMode, first_name: str) -> str:
    stem = Path(first_name).stem or "wottygif"
    suffix = "-combined" if mode == ProcessingMode.multi_image else ""
    return f"{stem}{suffix}.gif"


def source_name(mode: ProcessingMode, names: list[str]) -> str:
    if mode == ProcessingMode.multi_image:
        return f"{names[0]} +{len(names) - 1} 张图片"
    return names[0]


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "wottygif-api"}


@app.post("/api/media/jobs", response_model=MediaJob, status_code=201)
async def create_media_job(
    mode: ProcessingMode = Form(...),
    quality: int = Form(..., ge=1, le=5),
    origins: list[AssetOrigin] = Form(...),
    files: list[UploadFile] = File(...),
) -> MediaJob:
    kinds = validate_uploads(mode, files)
    asset_origins = normalized_origins(origins, len(files))
    job_id = uuid4().hex
    names = [Path(upload.filename or "asset").name for upload in files]
    assets = [
        MediaAsset(
            id=uuid4().hex,
            name=name,
            kind=kind,
            origin=origin,
            mime_type=upload.content_type or "application/octet-stream",
            size_bytes=max(upload.size or 0, 1),
        )
        for upload, name, kind, origin in zip(files, names, kinds, asset_origins)
    ]
    job = MediaJob(
        id=job_id,
        mode=mode,
        quality=quality,
        source_name=source_name(mode, names),
        asset_count=len(files),
        assets=assets,
        status=JobStatus.queued,
        created_at=datetime.now(timezone.utc),
        result_name=result_filename(mode, names[0]),
    )
    jobs[job_id] = job
    job.status = JobStatus.processing

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{job_id}.gif"

    try:
        with TemporaryDirectory(prefix="wottygif-") as temp_dir:
            input_paths: list[Path] = []
            for index, upload in enumerate(files):
                suffix = Path(upload.filename or "").suffix or ".bin"
                input_path = Path(temp_dir) / f"input-{index}{suffix}"
                size_bytes = await save_upload(upload, input_path)
                assets[index].size_bytes = max(size_bytes, 1)
                input_paths.append(input_path)

            if mode == ProcessingMode.video:
                generate_video_gif(input_paths[0], output_path, quality)
            else:
                generate_image_gif(input_paths, output_path, quality)

        result_paths[job_id] = output_path
        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        job.result_url = f"/api/media/jobs/{job_id}/result"
    except HTTPException:
        jobs.pop(job_id, None)
        raise
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        job.status = JobStatus.failed
        job.error_message = str(exc)

    return job


@app.get("/api/media/jobs", response_model=list[MediaJob])
def list_media_jobs() -> list[MediaJob]:
    return sorted(jobs.values(), key=lambda job: job.created_at, reverse=True)


@app.get("/api/media/jobs/{job_id}/result")
def get_media_result(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    result_path = result_paths.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.status != JobStatus.completed or not result_path or not result_path.exists():
        raise HTTPException(status_code=409, detail="任务尚未生成成品。")
    return FileResponse(
        result_path,
        media_type="image/gif",
        filename=job.result_name or f"{job_id}.gif",
        content_disposition_type="inline",
    )
