from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.adapters.inkstitch_adapter import InkstitchAdapter
from app.backend.main import app, app_state
from app.backend.services.job_service import JobService
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import LocalFileStorage


class DummyConverter(InkstitchAdapter):
    def __init__(self) -> None:
        pass

    def dependency_status(self):
        return True, True, None


class DummyWorker:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


def build_client(tmp_path: Path) -> TestClient:
    storage = LocalFileStorage(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        temp_dir=tmp_path / "temp",
        max_file_size=1024,
    )
    repository = JsonJobRepository(tmp_path / "jobs")
    storage.ensure_directories()
    repository.ensure_directories()
    worker = DummyWorker()
    app_state.storage = storage
    app_state.repository = repository
    app_state.converter = DummyConverter()
    app_state.worker = None
    app_state.job_service = JobService(
        repository=repository,
        storage=storage,
        worker=worker,
    )
    return TestClient(app)


def test_health(tmp_path):
    client = build_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["dependencies"]["inkscape"] is True


def test_create_svg_job(tmp_path):
    client = build_client(tmp_path)
    response = client.post(
        "/jobs",
        files={
            "file": (
                "test.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                "image/svg+xml",
            )
        },
        data={"output_format": "dst"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "RECEIVED"
    assert payload["output_format"] == "dst"


def test_reject_invalid_extension(tmp_path):
    client = build_client(tmp_path)
    response = client.post(
        "/jobs",
        files={
            "file": (
                "test.txt",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                "image/svg+xml",
            )
        },
        data={"output_format": "dst"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_file_type"


def test_reject_unsupported_output_format(tmp_path):
    client = build_client(tmp_path)
    response = client.post(
        "/jobs",
        files={
            "file": (
                "test.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                "image/svg+xml",
            )
        },
        data={"output_format": "pes"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_output_format"


def test_job_not_found(tmp_path):
    client = build_client(tmp_path)
    response = client.get(f"/jobs/{'b' * 32}")
    assert response.status_code == 404


def test_download_before_completion(tmp_path):
    client = build_client(tmp_path)
    create_response = client.post(
        "/jobs",
        files={
            "file": (
                "test.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                "image/svg+xml",
            )
        },
        data={"output_format": "dst"},
    )
    job_id = create_response.json()["job_id"]
    response = client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 409
    assert response.json()["error"] == "job_not_completed"
