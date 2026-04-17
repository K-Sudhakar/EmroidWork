from datetime import datetime

from pydantic import BaseModel

from app.backend.models.job import InputFormat, Job, JobStatus, OutputFormat


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
