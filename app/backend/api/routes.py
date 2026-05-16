from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.backend.core.config import Settings, get_settings
from app.backend.models.job import OutputFormat
from app.backend.schemas.job import (
    HealthDependencyStatus,
    HealthResponse,
    JobCreateResponse,
    JobMonitorResponse,
    JobResponse,
)
from app.backend.services.job_service import JobService

router = APIRouter()


def get_job_service() -> JobService:
    from app.backend.main import app_state

    if app_state.job_service is None:
        raise RuntimeError("Application services are not initialized.")
    return app_state.job_service


def get_converter():
    from app.backend.main import app_state

    if app_state.converter is None:
        raise RuntimeError("Application services are not initialized.")
    return app_state.converter


def get_vectorizer():
    from app.backend.main import app_state

    if app_state.vectorizer is None:
        raise RuntimeError("Application services are not initialized.")
    return app_state.vectorizer


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    converter=Depends(get_converter),
    vectorizer=Depends(get_vectorizer),
) -> HealthResponse:
    inkscape_ok, extension_ok, detail = converter.dependency_status()
    imagemagick_ok, potrace_ok, vectorizer_detail = vectorizer.dependency_status()
    status = "ok" if all([inkscape_ok, extension_ok, imagemagick_ok, potrace_ok]) else "degraded"
    return HealthResponse(
        status=status,
        app_name=settings.app_name,
        dependencies=HealthDependencyStatus(
            inkscape=inkscape_ok,
            inkstitch_extension=extension_ok,
            imagemagick=imagemagick_ok,
            potrace=potrace_ok,
            detail=detail or vectorizer_detail,
        ),
    )


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(
    file: UploadFile = File(...),
    output_format: OutputFormat = Form(OutputFormat.DST),
    service: JobService = Depends(get_job_service),
) -> JobCreateResponse:
    job = await service.create_job(upload=file, output_format=output_format)
    return JobCreateResponse.from_job(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = service.get_job(job_id)
    return JobResponse.from_job(job)


@router.get("/api/jobs", response_model=list[JobMonitorResponse])
def list_jobs(
    service: JobService = Depends(get_job_service),
) -> list[JobMonitorResponse]:
    return [JobMonitorResponse.from_job(job) for job in service.list_jobs()]


@router.get("/api/jobs/{job_id}/status", response_model=JobMonitorResponse)
def get_job_status(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobMonitorResponse:
    job = service.get_job(job_id)
    return JobMonitorResponse.from_job(job)


@router.get("/jobs/{job_id}/download")
def download_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> FileResponse:
    path = service.get_download_path(job_id)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )
