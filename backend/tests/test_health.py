from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_single_image_job() -> None:
    response = client.post(
        "/api/media/jobs",
        json={
            "mode": "single_image",
            "quality": 3,
            "assets": [
                {
                    "name": "poster-01.png",
                    "kind": "image",
                    "origin": "paste",
                    "mime_type": "image/png",
                    "size_bytes": 24012,
                },
                {
                    "name": "poster-02.png",
                    "kind": "image",
                    "origin": "upload",
                    "mime_type": "image/png",
                    "size_bytes": 27812,
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["mode"] == "single_image"
    assert body["quality"] == 3
    assert body["asset_count"] == 2


def test_reject_multi_image_with_one_asset() -> None:
    response = client.post(
        "/api/media/jobs",
        json={
            "mode": "multi_image",
            "quality": 4,
            "assets": [
                {
                    "name": "cover.png",
                    "kind": "image",
                    "origin": "upload",
                    "mime_type": "image/png",
                    "size_bytes": 9090,
                }
            ],
        },
    )

    assert response.status_code == 422


def test_reject_video_mode_with_image_assets() -> None:
    response = client.post(
        "/api/media/jobs",
        json={
            "mode": "video",
            "quality": 5,
            "assets": [
                {
                    "name": "shot.png",
                    "kind": "image",
                    "origin": "paste",
                    "mime_type": "image/png",
                    "size_bytes": 18000,
                }
            ],
        },
    )

    assert response.status_code == 422
