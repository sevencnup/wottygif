import base64
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main


client = TestClient(main.app)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    main.jobs.clear()
    main.result_paths.clear()
    main.job_device_ids.clear()


def gradient_image(path, width: int, height: int) -> None:
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (
                round(255 * x / max(width - 1, 1)),
                round(255 * y / max(height - 1, 1)),
                round(255 * (x + y) / max(width + height - 2, 1)),
            )
            for y in range(height)
            for x in range(width)
        ]
    )
    image.save(path)


def test_health_check() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_single_image_gif(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "single_image",
            "quality": "3",
            "origins": "upload",
        },
        files={"files": ("poster.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["result_url"]

    result = client.get(body["result_url"])
    assert result.status_code == 200
    assert result.headers["content-type"] == "image/gif"
    assert result.content.startswith(b"GIF")


def test_completed_jobs_survive_backend_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "single_image",
            "quality": "3",
            "origins": "upload",
        },
        files={"files": ("persistent.png", PNG_BYTES, "image/png")},
    )
    job_id = response.json()["id"]

    main.jobs.clear()
    main.result_paths.clear()
    main.load_persisted_jobs()

    listed = client.get("/api/media/jobs").json()
    assert [job["id"] for job in listed] == [job_id]
    assert listed[0]["status"] == "completed"
    assert client.get(listed[0]["result_url"]).content.startswith(b"GIF")


def test_orphaned_gif_is_recovered_as_historical_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    orphan_path = tmp_path / "orphan-result.gif"
    orphan_path.write_bytes(b"GIF89a")

    main.load_persisted_jobs()

    recovered = main.jobs["orphan-result"]
    assert recovered.status == main.JobStatus.completed
    assert recovered.source_name.startswith("历史成品")
    assert main.result_paths[recovered.id] == orphan_path


def test_cleanup_removes_only_completed_results_older_than_one_hour(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    now = datetime.now(timezone.utc)

    for job_id, age_minutes, status in (
        ("expired", 61, main.JobStatus.completed),
        ("fresh", 59, main.JobStatus.completed),
        ("failed", 120, main.JobStatus.failed),
    ):
        result_path = tmp_path / f"{job_id}.gif"
        result_path.write_bytes(b"GIF89a")
        job = main.MediaJob(
            id=job_id,
            mode=main.ProcessingMode.single_image,
            quality=3,
            source_name=f"{job_id}.png",
            asset_count=0,
            assets=[],
            status=status,
            created_at=now - timedelta(minutes=age_minutes),
            completed_at=(now - timedelta(minutes=age_minutes)) if status == main.JobStatus.completed else None,
            result_name=f"{job_id}.gif",
            result_url=f"/api/media/jobs/{job_id}/result" if status == main.JobStatus.completed else None,
        )
        main.jobs[job_id] = job
        main.result_paths[job_id] = result_path

    removed = main.cleanup_expired_results(now)

    assert removed == 1
    assert "expired" not in main.jobs
    assert "expired" not in main.result_paths
    assert not (tmp_path / "expired.gif").exists()
    assert (tmp_path / "fresh.gif").exists()
    assert (tmp_path / "failed.gif").exists()
    persisted_ids = {item["id"] for item in json.loads(main.jobs_metadata_path().read_text(encoding="utf-8"))}
    assert persisted_ids == {"fresh", "failed"}


def test_job_list_lazily_cleans_expired_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    completed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    result_path = tmp_path / "expired-on-list.gif"
    result_path.write_bytes(b"GIF89a")
    main.jobs["expired-on-list"] = main.MediaJob(
        id="expired-on-list",
        mode=main.ProcessingMode.single_image,
        quality=3,
        source_name="expired.png",
        asset_count=0,
        assets=[],
        status=main.JobStatus.completed,
        created_at=completed_at,
        completed_at=completed_at,
        result_name="expired.gif",
        result_url="/api/media/jobs/expired-on-list/result",
    )
    main.result_paths["expired-on-list"] = result_path

    response = client.get("/api/media/jobs")

    assert response.status_code == 200
    assert response.json() == []
    assert not result_path.exists()


def test_low_quality_gradient_keeps_smooth_palette(tmp_path) -> None:
    source = tmp_path / "gradient.png"
    result = tmp_path / "gradient.gif"
    gradient_image(source, 256, 128)

    main.generate_image_gif([source], result, quality=1)

    with Image.open(result) as image:
        colors = image.convert("RGB").getcolors(maxcolors=512)
    assert colors is not None
    assert len(colors) >= 100


def test_high_quality_preserves_large_image_width(tmp_path) -> None:
    source = tmp_path / "large-gradient.png"
    result = tmp_path / "large-gradient.gif"
    gradient_image(source, 1600, 32)

    main.generate_image_gif([source], result, quality=5)

    with Image.open(result) as image:
        assert image.width == 1600


def test_generate_image_gif_applies_per_image_crop(tmp_path) -> None:
    source = tmp_path / "crop-source.png"
    result = tmp_path / "crop-result.gif"
    gradient_image(source, 100, 60)

    main.generate_image_gif(
        [source],
        result,
        quality=4,
        crop_options=[
            main.ImageCropOptions(
                crop_left_percent=25,
                crop_top_percent=0,
                crop_width_percent=50,
                crop_height_percent=100,
            )
        ],
    )

    with Image.open(result) as image:
        assert image.size == (50, 60)


def test_image_job_accepts_ordered_crop_options(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    captured: dict[str, object] = {}

    def fake_generate_image_gif(input_paths, output_path, quality, crop_options=None):
        captured["crop_options"] = crop_options
        output_path.write_bytes(b"GIF89a")

    monkeypatch.setattr(main, "generate_image_gif", fake_generate_image_gif, raising=False)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "multi_image",
            "quality": "3",
            "origins": ["upload", "upload"],
            "image_crop_options": (
                '[{"crop_left_percent":10,"crop_top_percent":5,'
                '"crop_width_percent":60,"crop_height_percent":80},'
                '{"skip":true}]'
            ),
        },
        files=[
            ("files", ("first.png", PNG_BYTES, "image/png")),
            ("files", ("second.png", PNG_BYTES, "image/png")),
        ],
    )

    assert response.status_code == 201
    options = captured["crop_options"]
    assert len(options) == 2
    assert options[0].crop_left_percent == 10
    assert options[0].crop_width_percent == 60
    assert options[1].has_crop is False


def test_generate_multi_image_gif(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "multi_image",
            "quality": "4",
            "origins": "paste",
        },
        files=[
            ("files", ("first.png", PNG_BYTES, "image/png")),
            ("files", ("second.png", PNG_BYTES, "image/png")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["asset_count"] == 2
    assert body["result_name"] == "first-combined.gif"


def test_batch_download_contains_completed_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)

    for name in ("first.png", "second.png"):
        response = client.post(
            "/api/media/jobs",
            data={
                "mode": "single_image",
                "quality": "3",
                "origins": "upload",
            },
            files={"files": (name, PNG_BYTES, "image/png")},
        )
        assert response.json()["status"] == "completed"

    response = client.get("/api/media/jobs/batch-download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == ["first.gif", "second.gif"]
        assert all(archive.read(name).startswith(b"GIF") for name in archive.namelist())


def test_jobs_results_and_downloads_are_isolated_by_device(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    device_a = "device-aaaaaaaaaaaaaaaa"
    device_b = "device-bbbbbbbbbbbbbbbb"

    created = client.post(
        "/api/media/jobs",
        headers={"X-WottyGIF-Device-ID": device_a},
        data={
            "mode": "single_image",
            "quality": "3",
            "origins": "upload",
        },
        files={"files": ("private.png", PNG_BYTES, "image/png")},
    ).json()

    assert [job["id"] for job in client.get(
        "/api/media/jobs", headers={"X-WottyGIF-Device-ID": device_a}
    ).json()] == [created["id"]]
    assert client.get(
        "/api/media/jobs", headers={"X-WottyGIF-Device-ID": device_b}
    ).json() == []
    assert client.get(f'{created["result_url"]}?device_id={device_a}').status_code == 200
    assert client.get(f'{created["result_url"]}?device_id={device_b}').status_code == 404
    assert client.get(f"/api/media/jobs/batch-download?device_id={device_b}").status_code == 409


def test_reject_video_longer_than_30_seconds(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(main, "probe_video_duration", lambda _: 31.0, raising=False)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "video",
            "quality": "3",
            "origins": "upload",
        },
        files={"files": ("long.mp4", b"not-a-real-video", "video/mp4")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert "30" in body["error_message"]


def test_allow_trimmed_segment_from_long_video(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "result.gif"
    input_path.write_bytes(b"video")
    captured: dict[str, object] = {}

    monkeypatch.setattr(main, "probe_video_duration", lambda _: 80.0, raising=False)
    monkeypatch.setattr(main, "find_ffmpeg", lambda: "ffmpeg", raising=False)

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_path.write_bytes(b"GIF89a")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(main.subprocess, "run", fake_run, raising=False)

    main.generate_video_gif(
        input_path,
        output_path,
        quality=3,
        options=main.VideoEditOptions(
            clip_start_seconds=5.0,
            clip_end_seconds=17.5,
            crop_left_percent=10.0,
            crop_top_percent=5.0,
            crop_width_percent=60.0,
            crop_height_percent=70.0,
        ),
    )

    command = captured["command"]
    assert output_path.exists()
    assert "-ss" in command and "5.000" in command
    assert "-t" in command and "12.500" in command
    filter_text = command[command.index("-vf") + 1]
    assert "crop=" in filter_text
    assert "fps=10" in filter_text


def test_video_job_accepts_trim_and_crop_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path)
    captured: dict[str, object] = {}

    def fake_generate_video_gif(input_path, output_path, quality, options):
        captured["quality"] = quality
        captured["options"] = options
        output_path.write_bytes(b"GIF89a")

    monkeypatch.setattr(main, "generate_video_gif", fake_generate_video_gif, raising=False)

    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "video",
            "quality": "3",
            "origins": "upload",
            "clip_start_seconds": "3.5",
            "clip_end_seconds": "18",
            "crop_left_percent": "8",
            "crop_top_percent": "4",
            "crop_width_percent": "72",
            "crop_height_percent": "66",
        },
        files={"files": ("clip.mp4", b"video", "video/mp4")},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    options = captured["options"]
    assert captured["quality"] == 3
    assert options.clip_start_seconds == 3.5
    assert options.clip_end_seconds == 18.0
    assert options.crop_width_percent == 72.0


def test_reject_multi_image_with_one_asset() -> None:
    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "multi_image",
            "quality": "4",
            "origins": "upload",
        },
        files={"files": ("cover.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 422


def test_reject_video_mode_with_image_assets() -> None:
    response = client.post(
        "/api/media/jobs",
        data={
            "mode": "video",
            "quality": "5",
            "origins": "paste",
        },
        files={"files": ("shot.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 422
