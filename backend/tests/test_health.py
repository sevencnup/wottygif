import base64

from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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
