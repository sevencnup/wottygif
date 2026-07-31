from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class JobType(StrEnum):
    image_to_gif = "image_to_gif"
    video_to_gif = "video_to_gif"


class JobStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class CreateMediaJob(BaseModel):
    job_type: JobType = Field(..., description="Media processing workflow type.")
    source_name: str = Field(..., min_length=1, max_length=240)


class MediaJob(BaseModel):
    id: str
    job_type: JobType
    source_name: str
    status: JobStatus
    created_at: datetime


app = FastAPI(title="WottyGIF API", version="0.1.0")

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


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "wottygif-api",
    }


@app.post("/api/media/jobs", response_model=MediaJob, status_code=201)
def create_media_job(payload: CreateMediaJob) -> MediaJob:
    job = MediaJob(
        id=uuid4().hex,
        job_type=payload.job_type,
        source_name=payload.source_name,
        status=JobStatus.queued,
        created_at=datetime.now(timezone.utc),
    )
    jobs[job.id] = job
    return job


@app.get("/api/media/jobs", response_model=list[MediaJob])
def list_media_jobs() -> list[MediaJob]:
    return sorted(jobs.values(), key=lambda job: job.created_at, reverse=True)
