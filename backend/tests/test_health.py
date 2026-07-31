from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_media_job() -> None:
    response = client.post(
        "/api/media/jobs",
        json={"job_type": "image_to_gif", "source_name": "demo.png"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["source_name"] == "demo.png"
