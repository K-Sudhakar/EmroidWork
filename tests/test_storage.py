from app.backend.models.job import Job, JobStatus, OutputFormat
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import sanitize_filename


def test_sanitize_filename_removes_paths_and_unsafe_characters():
    assert sanitize_filename("../unsafe name.svg") == "unsafe_name.svg"


def test_json_job_repository_create_update_read(tmp_path):
    repository = JsonJobRepository(tmp_path)
    repository.ensure_directories()
    job_id = "a" * 32
    job = Job(
        job_id=job_id,
        filename="input.svg",
        input_path=tmp_path / "input.svg",
        output_format=OutputFormat.DST,
    )

    repository.create(job)
    saved = repository.get(job_id)
    assert saved.job_id == job_id

    updated = repository.update(saved.with_status(JobStatus.PROCESSING))
    assert updated.status == JobStatus.PROCESSING
    assert repository.get(job_id).status == JobStatus.PROCESSING
