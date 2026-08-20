from __future__ import annotations

import asyncio
import os
import json
import logging
import re
import shutil
import subprocess
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel
from starlette.background import BackgroundTask


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    cleanup_expired_results()
    cleanup_task = asyncio.create_task(cleanup_expired_results_periodically())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


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


app = FastAPI(title="WottyGIF API", version="0.3.27", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:23689",
        "http://127.0.0.1:23689",
    ],
    allow_origin_regex=r"http://(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}):23689",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "data" / "results"
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_ASSETS = 24
MAX_VIDEO_SECONDS = 30.0
RESULT_RETENTION = timedelta(hours=1)
RESULT_CLEANUP_INTERVAL_SECONDS = 60
LEGACY_DEVICE_ID = "legacy-unassigned"
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
QUALITY_SETTINGS = {
    1: {"max_side": 360, "colors": 128, "fps": 6, "kmeans": 0},
    2: {"max_side": 540, "colors": 160, "fps": 8, "kmeans": 1},
    3: {"max_side": 720, "colors": 192, "fps": 10, "kmeans": 1},
    4: {"max_side": 1080, "colors": 224, "fps": 12, "kmeans": 2},
    5: {"max_side": 1920, "colors": 256, "fps": 15, "kmeans": 3},
}

jobs: dict[str, MediaJob] = {}
result_paths: dict[str, Path] = {}
job_device_ids: dict[str, str] = {}


def normalized_device_id(value: str | None) -> str:
    if value is None:
        return LEGACY_DEVICE_ID
    if not DEVICE_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=400, detail="设备标识格式无效。")
    return value


def jobs_metadata_path() -> Path:
    return RESULTS_DIR / "jobs.json"


def persist_jobs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = jobs_metadata_path()
    temporary_path = metadata_path.with_name(f".{metadata_path.name}.{uuid4().hex}.tmp")
    payload = []
    for job in sorted(jobs.values(), key=lambda item: item.created_at, reverse=True):
        item = job.model_dump(mode="json")
        item["_device_id"] = job_device_ids.get(job.id, LEGACY_DEVICE_ID)
        payload.append(item)
    try:
        temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(metadata_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def historical_job(result_path: Path) -> MediaJob:
    completed_at = datetime.fromtimestamp(result_path.stat().st_mtime, tz=timezone.utc)
    timestamp = completed_at.astimezone().strftime("%Y%m%d-%H%M%S")
    return MediaJob(
        id=result_path.stem,
        mode=ProcessingMode.single_image,
        quality=3,
        source_name=f"历史成品 {completed_at.astimezone().strftime('%Y-%m-%d %H:%M')}",
        asset_count=0,
        assets=[],
        status=JobStatus.completed,
        created_at=completed_at,
        completed_at=completed_at,
        result_name=f"历史成品-{timestamp}.gif",
        result_url=f"/api/media/jobs/{result_path.stem}/result",
    )


def cleanup_expired_results(
    now: datetime | None = None,
    *,
    save_metadata: bool = True,
) -> int:
    current_time = now or datetime.now(timezone.utc)
    expired_ids: list[str] = []

    for job_id, job in list(jobs.items()):
        if job.status != JobStatus.completed:
            continue
        completed_at = job.completed_at or job.created_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        if current_time - completed_at < RESULT_RETENTION:
            continue

        result_path = result_paths.get(job_id)
        if result_path:
            try:
                result_path.unlink(missing_ok=True)
            except OSError:
                if result_path.exists():
                    logger.warning("Unable to remove expired GIF result: %s", result_path)
                    continue

        result_paths.pop(job_id, None)
        job_device_ids.pop(job_id, None)
        jobs.pop(job_id, None)
        expired_ids.append(job_id)

    if expired_ids and save_metadata:
        persist_jobs()
    if expired_ids:
        logger.info("Removed %d expired GIF result(s).", len(expired_ids))
    return len(expired_ids)


async def cleanup_expired_results_periodically() -> None:
    while True:
        await asyncio.sleep(RESULT_CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_expired_results()
        except Exception:
            logger.exception("Periodic GIF result cleanup failed.")


def load_persisted_jobs() -> None:
    jobs.clear()
    result_paths.clear()
    job_device_ids.clear()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = jobs_metadata_path()

    if metadata_path.exists():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                job_payload = dict(item)
                device_id = job_payload.pop("_device_id", LEGACY_DEVICE_ID)
                if not isinstance(device_id, str) or not DEVICE_ID_PATTERN.fullmatch(device_id):
                    device_id = LEGACY_DEVICE_ID
                try:
                    job = MediaJob.model_validate(job_payload)
                except (TypeError, ValueError):
                    continue
                result_path = RESULTS_DIR / f"{job.id}.gif"
                if job.status == JobStatus.completed:
                    if not result_path.exists():
                        continue
                    result_paths[job.id] = result_path
                elif job.status in {JobStatus.queued, JobStatus.processing}:
                    job.status = JobStatus.failed
                    job.error_message = "任务因后端服务重启而中断。"
                jobs[job.id] = job
                job_device_ids[job.id] = device_id

    for result_path in RESULTS_DIR.glob("*.gif"):
        if result_path.stem in jobs:
            continue
        job = historical_job(result_path)
        jobs[job.id] = job
        result_paths[job.id] = result_path
        job_device_ids[job.id] = LEGACY_DEVICE_ID

    cleanup_expired_results(save_metadata=False)
    persist_jobs()


load_persisted_jobs()


@dataclass
class VideoEditOptions:
    clip_start_seconds: float = 0.0
    clip_end_seconds: float | None = None
    crop_left_percent: float = 0.0
    crop_top_percent: float = 0.0
    crop_width_percent: float = 100.0
    crop_height_percent: float = 100.0

    @property
    def has_crop(self) -> bool:
        return (
            abs(self.crop_left_percent) > 1e-6
            or abs(self.crop_top_percent) > 1e-6
            or abs(self.crop_width_percent - 100.0) > 1e-6
            or abs(self.crop_height_percent - 100.0) > 1e-6
        )


@dataclass
class ImageCropOptions:
    crop_left_percent: float = 0.0
    crop_top_percent: float = 0.0
    crop_width_percent: float = 100.0
    crop_height_percent: float = 100.0

    @property
    def has_crop(self) -> bool:
        return (
            abs(self.crop_left_percent) > 1e-6
            or abs(self.crop_top_percent) > 1e-6
            or abs(self.crop_width_percent - 100.0) > 1e-6
            or abs(self.crop_height_percent - 100.0) > 1e-6
        )


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
        raise HTTPException(status_code=422, detail="单张图转GIF每个任务只能上传一张图片。")
    if mode == ProcessingMode.multi_image and (len(uploads) < 2 or any(kind != AssetKind.image for kind in kinds)):
        raise HTTPException(status_code=422, detail="多图合成GIF至少需要两张图片。")
    if mode == ProcessingMode.video and (len(uploads) != 1 or kinds[0] != AssetKind.video):
        raise HTTPException(status_code=422, detail="视频转GIF每个任务只能上传一个视频。")
    return kinds


def normalized_origins(origins: list[AssetOrigin], asset_count: int) -> list[AssetOrigin]:
    if len(origins) == 1:
        return origins * asset_count
    if len(origins) != asset_count:
        raise HTTPException(status_code=422, detail="素材来源数量与上传文件数量不一致。")
    return origins


def build_video_edit_options(
    mode: ProcessingMode,
    clip_start_seconds: float | None,
    clip_end_seconds: float | None,
    crop_left_percent: float | None,
    crop_top_percent: float | None,
    crop_width_percent: float | None,
    crop_height_percent: float | None,
) -> VideoEditOptions:
    if mode != ProcessingMode.video:
        return VideoEditOptions()

    options = VideoEditOptions(
        clip_start_seconds=clip_start_seconds or 0.0,
        clip_end_seconds=clip_end_seconds,
        crop_left_percent=crop_left_percent or 0.0,
        crop_top_percent=crop_top_percent or 0.0,
        crop_width_percent=crop_width_percent or 100.0,
        crop_height_percent=crop_height_percent or 100.0,
    )

    if options.clip_end_seconds is not None and options.clip_end_seconds <= options.clip_start_seconds:
        raise HTTPException(status_code=422, detail="结束时间必须大于开始时间。")

    if options.crop_left_percent + options.crop_width_percent > 100.0 + 1e-6:
        raise HTTPException(status_code=422, detail="裁剪区域超出画面宽度，请调整左边距或裁剪宽度。")

    if options.crop_top_percent + options.crop_height_percent > 100.0 + 1e-6:
        raise HTTPException(status_code=422, detail="裁剪区域超出画面高度，请调整上边距或裁剪高度。")

    return options


def build_image_crop_options(
    mode: ProcessingMode,
    raw_options: str | None,
    asset_count: int,
) -> list[ImageCropOptions]:
    defaults = [ImageCropOptions() for _ in range(asset_count)]
    if mode == ProcessingMode.video or not raw_options:
        return defaults

    try:
        payload = json.loads(raw_options)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="图片裁剪参数不是有效的 JSON。") from exc

    if not isinstance(payload, list) or len(payload) != asset_count:
        raise HTTPException(status_code=422, detail="图片裁剪参数数量必须与上传图片数量一致。")

    options: list[ImageCropOptions] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片的裁剪参数格式不正确。")
        if item.get("skip") is True:
            options.append(ImageCropOptions())
            continue

        try:
            crop = ImageCropOptions(
                crop_left_percent=float(item.get("crop_left_percent", 0)),
                crop_top_percent=float(item.get("crop_top_percent", 0)),
                crop_width_percent=float(item.get("crop_width_percent", 100)),
                crop_height_percent=float(item.get("crop_height_percent", 100)),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片包含无效裁剪数字。") from exc

        if crop.crop_left_percent < 0 or crop.crop_top_percent < 0:
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片的裁剪位置不能小于 0。")
        if not 0 < crop.crop_width_percent <= 100 or not 0 < crop.crop_height_percent <= 100:
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片的裁剪宽高必须在 0 到 100 之间。")
        if crop.crop_left_percent + crop.crop_width_percent > 100 + 1e-6:
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片的裁剪区域超出画面宽度。")
        if crop.crop_top_percent + crop.crop_height_percent > 100 + 1e-6:
            raise HTTPException(status_code=422, detail=f"第 {index + 1} 张图片的裁剪区域超出画面高度。")
        options.append(crop)

    return options


async def save_upload(upload: UploadFile, destination: Path) -> int:
    total = 0
    with destination.open("wb") as target:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail=f"文件 {upload.filename} 超过 200 MB。")
            target.write(chunk)
    return total


def prepare_image(
    path: Path,
    max_side: int,
    crop_options: ImageCropOptions | None = None,
) -> Image.Image:
    try:
        with Image.open(path) as source:
            frame = ImageOps.exif_transpose(source).convert("RGB")
            crop = crop_options or ImageCropOptions()
            if crop.has_crop:
                left = min(round(frame.width * crop.crop_left_percent / 100), frame.width - 1)
                top = min(round(frame.height * crop.crop_top_percent / 100), frame.height - 1)
                right = round(frame.width * (crop.crop_left_percent + crop.crop_width_percent) / 100)
                bottom = round(frame.height * (crop.crop_top_percent + crop.crop_height_percent) / 100)
                right = min(max(right, left + 1), frame.width)
                bottom = min(max(bottom, top + 1), frame.height)
                frame = frame.crop((left, top, right, bottom))
            frame.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            return frame.copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"无法读取图片 {path.name}") from exc


def generate_image_gif(
    input_paths: list[Path],
    output_path: Path,
    quality: int,
    crop_options: list[ImageCropOptions] | None = None,
    fps: int | None = None,
) -> None:
    settings = QUALITY_SETTINGS[quality]
    options = crop_options or [ImageCropOptions() for _ in input_paths]
    if len(options) != len(input_paths):
        raise ValueError("图片裁剪参数数量与输入图片数量不一致。")
    frame_rate = fps or settings["fps"]
    frame_duration = max(1, round(1000 / frame_rate))
    source_frames = [
        prepare_image(path, settings["max_side"], crop)
        for path, crop in zip(input_paths, options)
    ]
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
                kmeans=settings["kmeans"],
                dither=Image.Dither.NONE,
            )
        )

    frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=0,
        optimize=False,
        disposal=2,
    )


def find_ffmpeg() -> str:
    configured = os.environ.get("WOTTYGIF_FFMPEG")
    executable = configured or shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("未找到 FFmpeg，请安装后加入 PATH，或设置 WOTTYGIF_FFMPEG。")
    return executable


def find_ffprobe() -> str:
    configured = os.environ.get("WOTTYGIF_FFPROBE")
    executable = configured or shutil.which("ffprobe")
    if executable:
        return executable

    ffmpeg_path = Path(find_ffmpeg())
    sibling = ffmpeg_path.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    raise RuntimeError("未找到 FFprobe，请安装后加入 PATH，或设置 WOTTYGIF_FFPROBE。")


def probe_video_duration(input_path: Path) -> float:
    completed = subprocess.run(
        [
            find_ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "无法读取视频时长。"
        raise ValueError(detail[-600:])
    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise ValueError("无法读取视频时长。") from exc


def resolve_video_clip(duration: float, options: VideoEditOptions) -> tuple[float, float]:
    if options.clip_start_seconds >= duration - 0.05:
        raise ValueError(f"开始时间 {options.clip_start_seconds:.2f} 秒已超出视频时长 {duration:.2f} 秒。")

    clip_end_seconds = options.clip_end_seconds if options.clip_end_seconds is not None else duration
    if clip_end_seconds > duration + 0.05:
        raise ValueError(f"结束时间 {clip_end_seconds:.2f} 秒超出视频时长 {duration:.2f} 秒。")

    clip_duration = clip_end_seconds - options.clip_start_seconds
    if clip_duration <= 0.05:
        raise ValueError("截取时长至少需要大于 0.05 秒。")
    if clip_duration > MAX_VIDEO_SECONDS + 0.05:
        raise ValueError(f"当前截取片段为 {clip_duration:.1f} 秒，最长支持 30 秒，请缩短后重试。")

    return clip_end_seconds, clip_duration


def build_video_filter(quality: int, options: VideoEditOptions) -> str:
    settings = QUALITY_SETTINGS[quality]
    filter_steps: list[str] = []
    if options.has_crop:
        filter_steps.append(
            "crop="
            f"'floor(iw*{options.crop_width_percent / 100:.6f}/2)*2':"
            f"'floor(ih*{options.crop_height_percent / 100:.6f}/2)*2':"
            f"'floor(iw*{options.crop_left_percent / 100:.6f}/2)*2':"
            f"'floor(ih*{options.crop_top_percent / 100:.6f}/2)*2'"
        )

    filter_steps.extend(
        [
            f"fps={settings['fps']}",
            f"scale='min({settings['max_side']},iw)':-2:flags=lanczos",
        ]
    )
    return (
        ",".join(filter_steps)
        + ","
        f"split[source][palette_input];[palette_input]palettegen=max_colors={settings['colors']}:"
        "reserve_transparent=0:stats_mode=full[palette];"
        "[source][palette]paletteuse=dither=none"
    )


def generate_video_gif(
    input_path: Path,
    output_path: Path,
    quality: int,
    options: VideoEditOptions | None = None,
) -> None:
    edit_options = options or VideoEditOptions()
    duration = probe_video_duration(input_path)
    _, clip_duration = resolve_video_clip(duration, edit_options)
    video_filter = build_video_filter(quality, edit_options)
    command = [
        find_ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
    ]
    if edit_options.clip_start_seconds > 0:
        command.extend(["-ss", f"{edit_options.clip_start_seconds:.3f}"])
    command.extend(["-t", f"{clip_duration:.3f}", "-vf", video_filter, str(output_path)])

    completed = subprocess.run(
        command,
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
    fps: int | None = Form(None, ge=1, le=30),
    origins: list[AssetOrigin] = Form(...),
    clip_start_seconds: float | None = Form(None, ge=0),
    clip_end_seconds: float | None = Form(None, gt=0),
    crop_left_percent: float | None = Form(None, ge=0, le=100),
    crop_top_percent: float | None = Form(None, ge=0, le=100),
    crop_width_percent: float | None = Form(None, gt=0, le=100),
    crop_height_percent: float | None = Form(None, gt=0, le=100),
    image_crop_options: str | None = Form(None),
    files: list[UploadFile] = File(...),
    device_id: str | None = Header(None, alias="X-WottyGIF-Device-ID"),
) -> MediaJob:
    requester_device_id = normalized_device_id(device_id)
    kinds = validate_uploads(mode, files)
    asset_origins = normalized_origins(origins, len(files))
    video_edit_options = build_video_edit_options(
        mode,
        clip_start_seconds,
        clip_end_seconds,
        crop_left_percent,
        crop_top_percent,
        crop_width_percent,
        crop_height_percent,
    )
    image_edit_options = build_image_crop_options(mode, image_crop_options, len(files))
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
    job_device_ids[job_id] = requester_device_id
    job.status = JobStatus.processing

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{job_id}.gif"
    persist_jobs()

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
                generate_video_gif(input_paths[0], output_path, quality, video_edit_options)
            else:
                generate_image_gif(input_paths, output_path, quality, image_edit_options, fps=fps)

        result_paths[job_id] = output_path
        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        job.result_url = f"/api/media/jobs/{job_id}/result"
        persist_jobs()
    except HTTPException:
        jobs.pop(job_id, None)
        job_device_ids.pop(job_id, None)
        persist_jobs()
        raise
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        job.status = JobStatus.failed
        job.error_message = str(exc)
        persist_jobs()

    return job


@app.get("/api/media/jobs", response_model=list[MediaJob])
def list_media_jobs(
    device_id: str | None = Header(None, alias="X-WottyGIF-Device-ID"),
) -> list[MediaJob]:
    cleanup_expired_results()
    requester_device_id = normalized_device_id(device_id)
    visible_jobs = [
        job for job in jobs.values() if job_device_ids.get(job.id, LEGACY_DEVICE_ID) == requester_device_id
    ]
    return sorted(visible_jobs, key=lambda job: job.created_at, reverse=True)


def archive_name(filename: str, used_names: set[str]) -> str:
    safe_name = Path(filename).name or "wottygif.gif"
    candidate = safe_name
    index = 2
    while candidate.lower() in used_names:
        path = Path(safe_name)
        candidate = f"{path.stem}-{index}{path.suffix}"
        index += 1
    used_names.add(candidate.lower())
    return candidate


@app.get("/api/media/jobs/batch-download")
def batch_download_results(
    device_id: str | None = Query(None),
) -> FileResponse:
    cleanup_expired_results()
    requester_device_id = normalized_device_id(device_id)
    completed_results = [
        (job, result_paths[job.id])
        for job in sorted(jobs.values(), key=lambda item: item.created_at)
        if job.status == JobStatus.completed
        and job_device_ids.get(job.id, LEGACY_DEVICE_ID) == requester_device_id
        and job.id in result_paths
        and result_paths[job.id].exists()
    ]
    if not completed_results:
        raise HTTPException(status_code=409, detail="当前没有可下载的 GIF 成品。")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix="wottygif-batch-", suffix=".zip", dir=RESULTS_DIR, delete=False) as temporary:
        archive_path = Path(temporary.name)

    used_names: set[str] = set()
    try:
        with ZipFile(archive_path, "w", compression=ZIP_STORED) as archive:
            for job, result_path in completed_results:
                archive.write(
                    result_path,
                    archive_name(job.result_name or f"{job.id}.gif", used_names),
                )
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="wottygif-results.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@app.get("/api/media/jobs/{job_id}/result")
def get_media_result(
    job_id: str,
    device_id: str | None = Query(None),
) -> FileResponse:
    cleanup_expired_results()
    requester_device_id = normalized_device_id(device_id)
    job = jobs.get(job_id)
    result_path = result_paths.get(job_id)
    if not job or job_device_ids.get(job_id, LEGACY_DEVICE_ID) != requester_device_id:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.status != JobStatus.completed or not result_path or not result_path.exists():
        raise HTTPException(status_code=409, detail="任务尚未生成成品。")
    return FileResponse(
        result_path,
        media_type="image/gif",
        filename=job.result_name or f"{job_id}.gif",
        content_disposition_type="inline",
    )
