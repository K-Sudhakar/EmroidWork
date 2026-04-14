from pathlib import Path
from uuid import uuid4

from starlette.datastructures import UploadFile

from app.backend.core.errors import ConflictAppError, NotFoundAppError, UnprocessableAppError
from app.backend.models.job import SUPPORTED_OUTPUT_FORMATS, Job, JobStatus, OutputFormat
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import LocalFileStorage
from app.backend.workers.job_worker import JobWorker


class JobService:
    def __init__(
        self,
        *,
        repository: JsonJobRepository,
        storage: LocalFileStorage,
        worker: JobWorker,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.worker = worker

    async def create_job(self, *, upload: UploadFile, output_format: OutputFormat) -> Job:
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise UnprocessableAppError(
                f"Output format '{output_format.value}' is not supported in this MVP.",
                code="unsupported_output_format",
            )

        job_id = uuid4().hex
        filename, input_path = await self.storage.save_svg_upload(job_id, upload)
        job = Job(
            job_id=job_id,
            filename=filename,
            input_path=input_path,
            output_format=output_format,
            status=JobStatus.RECEIVED,
        )
        self.repository.create(job)
        self.worker.enqueue(job.job_id)
        return job

    def get_job(self, job_id: str) -> Job:
        return self.repository.get(job_id)

    def get_download_path(self, job_id: str) -> Path:
        job = self.repository.get(job_id)
        if job.status == JobStatus.FAILED:
            raise ConflictAppError("Job failed and no output is available.", code="job_failed")
        if job.status != JobStatus.COMPLETED:
            raise ConflictAppError(
                "Job output is not ready yet.",
                code="job_not_completed",
            )
        if not job.output_path or not job.output_path.exists():
            raise NotFoundAppError("Job output file was not found.", code="output_not_found")
        return job.output_path
