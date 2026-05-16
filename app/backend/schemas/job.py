from datetime import UTC, datetime

from pydantic import BaseModel

from app.backend.models.job import InputFormat, Job, JobStatus, OutputFormat


_STATUS_PROGRESS = {
    JobStatus.RECEIVED: 10,
    JobStatus.VALIDATING: 35,
    JobStatus.PROCESSING: 70,
    JobStatus.COMPLETED: 100,
    JobStatus.FAILED: 100,
}


class JobCreateResponse(BaseModel):
    job_id: str
    filename: str
    input_format: InputFormat
    output_format: OutputFormat
    status: JobStatus
    created_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobCreateResponse":
        return cls(
            job_id=job.job_id,
            filename=job.filename,
            input_format=job.input_format,
            output_format=job.output_format,
            status=job.status,
            created_at=job.created_at,
        )


class JobResponse(BaseModel):
    job_id: str
    filename: str
    input_format: InputFormat
    output_format: OutputFormat
    status: JobStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    download_url: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        download_url = (
            f"/jobs/{job.job_id}/download"
            if job.status == JobStatus.COMPLETED and job.output_path
            else None
        )
        return cls(
            job_id=job.job_id,
            filename=job.filename,
            input_format=job.input_format,
            output_format=job.output_format,
            status=job.status,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            download_url=download_url,
        )


class JobMonitorResponse(BaseModel):
    job_id: str
    job_type: str
    name: str
    status: JobStatus
    progress_percent: int
    start_time: datetime
    end_time: datetime | None = None
    duration_seconds: float | None = None
    last_updated_time: datetime
    error_message: str | None = None
    download_url: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobMonitorResponse":
        is_finished = job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
        end_time = job.updated_at if is_finished else None
        duration_end = end_time or datetime.now(UTC)
        duration_seconds = round((duration_end - job.created_at).total_seconds(), 3)
        download_url = (
            f"/jobs/{job.job_id}/download"
            if job.status == JobStatus.COMPLETED and job.output_path
            else None
        )
        return cls(
            job_id=job.job_id,
            job_type=f"{job.input_format.value}->{job.output_format.value}",
            name=job.filename,
            status=job.status,
            progress_percent=_STATUS_PROGRESS[job.status],
            start_time=job.created_at,
            end_time=end_time,
            duration_seconds=duration_seconds,
            last_updated_time=job.updated_at,
            error_message=job.error_message,
            download_url=download_url,
        )


class HealthDependencyStatus(BaseModel):
    inkscape: bool
    inkstitch_extension: bool
    imagemagick: bool
    potrace: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    dependencies: HealthDependencyStatus


class ErrorResponse(BaseModel):
    error: str
    message: str
