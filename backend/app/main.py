from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator


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


class MediaAssetInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=240)
    kind: AssetKind
    origin: AssetOrigin
    mime_type: str = Field(..., min_length=1, max_length=120)
    size_bytes: int = Field(..., ge=1)


class CreateMediaJob(BaseModel):
    mode: ProcessingMode
    quality: int = Field(..., ge=1, le=5)
    assets: list[MediaAssetInput] = Field(..., min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_mode_assets(self) -> "CreateMediaJob":
        image_count = sum(1 for asset in self.assets if asset.kind == AssetKind.image)
        video_count = sum(1 for asset in self.assets if asset.kind == AssetKind.video)

        if self.mode == ProcessingMode.single_image:
            if image_count != len(self.assets):
                raise ValueError("Single image mode only accepts image assets.")
        elif self.mode == ProcessingMode.multi_image:
            if image_count != len(self.assets):
                raise ValueError("Multi-image mode only accepts image assets.")
            if image_count < 2:
                raise ValueError("Multi-image mode requires at least two images.")
        elif self.mode == ProcessingMode.video:
            if video_count != len(self.assets):
                raise ValueError("Video mode only accepts video assets.")

        return self


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


app = FastAPI(title="WottyGIF API", version="0.2.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, MediaJob] = {}


def build_source_name(mode: ProcessingMode, assets: list[MediaAssetInput]) -> str:
    first_asset = assets[0].name
    extra_count = len(assets) - 1

    if mode == ProcessingMode.single_image:
        return first_asset if extra_count == 0 else f"{first_asset} +{extra_count} single image items"
    if mode == ProcessingMode.multi_image:
        return f"{first_asset} +{extra_count} images combined"
    return first_asset if extra_count == 0 else f"{first_asset} +{extra_count} video items"


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "wottygif-api",
    }


@app.post("/api/media/jobs", response_model=MediaJob, status_code=201)
def create_media_job(payload: CreateMediaJob) -> MediaJob:
    assets = [
        MediaAsset(
            id=uuid4().hex,
            name=asset.name,
            kind=asset.kind,
            origin=asset.origin,
            mime_type=asset.mime_type,
            size_bytes=asset.size_bytes,
        )
        for asset in payload.assets
    ]
    job = MediaJob(
        id=uuid4().hex,
        mode=payload.mode,
        quality=payload.quality,
        source_name=build_source_name(payload.mode, payload.assets),
        asset_count=len(assets),
        assets=assets,
        status=JobStatus.queued,
        created_at=datetime.now(timezone.utc),
    )
    jobs[job.id] = job
    return job


@app.get("/api/media/jobs", response_model=list[MediaJob])
def list_media_jobs() -> list[MediaJob]:
    return sorted(jobs.values(), key=lambda job: job.created_at, reverse=True)
