from app.backend.adapters.inkstitch_adapter import InkstitchExecutionError
from app.backend.adapters.svg_preflight import SvgPreflightError
from app.backend.models.job import Job, JobStatus, OutputFormat
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import LocalFileStorage
from app.backend.workers.job_worker import JobWorker
from app.backend.workers.job_worker import _format_conversion_error


def test_format_conversion_error_includes_stderr_summary():
    error = InkstitchExecutionError(
        "Ink/Stitch conversion failed.",
        stderr="first line\nsecond line",
        exit_code=1,
    )

    assert (
        _format_conversion_error(error)
        == "Ink/Stitch conversion failed. Detail: first line second line"
    )


def test_format_conversion_error_uses_message_without_stderr():
    error = InkstitchExecutionError("Ink/Stitch conversion failed.", stderr="")

    assert _format_conversion_error(error) == "Ink/Stitch conversion failed."


def test_format_conversion_error_uses_stdout_when_stderr_is_empty():
    error = InkstitchExecutionError(
        "Ink/Stitch did not return a valid zip export archive.",
        stdout="Ink/Stitch warning: no stitchable elements found",
    )

    assert (
        _format_conversion_error(error)
        == "Ink/Stitch did not return a valid zip export archive. Detail: Ink/Stitch warning: no stitchable elements found"
    )


class RejectingPreflight:
    def validate(self, _path):
        raise SvgPreflightError("SVG is too complex for conversion.")


class UnusedConverter:
    def convert(self, **_kwargs):
        raise AssertionError("converter should not run after preflight failure")


class UnusedVectorizer:
    pass


def test_worker_fails_job_when_svg_preflight_rejects_input(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    temp_dir = tmp_path / "temp"
    storage = LocalFileStorage(
        input_dir=input_dir,
        output_dir=output_dir,
        temp_dir=temp_dir,
        max_file_size=1024,
    )
    repository = JsonJobRepository(tmp_path / "jobs")
    storage.ensure_directories()
    repository.ensure_directories()

    job_id = "a" * 32
    job_input_dir = input_dir / job_id
    job_input_dir.mkdir()
    input_path = job_input_dir / "input.svg"
    input_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    repository.create(
        Job(
            job_id=job_id,
            filename="input.svg",
            input_path=input_path,
            output_format=OutputFormat.DST,
        )
    )
    worker = JobWorker(
        repository=repository,
        storage=storage,
        converter=UnusedConverter(),
        vectorizer=UnusedVectorizer(),
        svg_preflight=RejectingPreflight(),
    )

    worker._process(job_id)

    saved = repository.get(job_id)
    assert saved.status == JobStatus.FAILED
    assert saved.error_message == "SVG is too complex for conversion."
