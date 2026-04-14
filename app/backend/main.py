from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.backend.adapters.inkstitch_adapter import InkstitchAdapter
from app.backend.api.routes import router
from app.backend.core.config import get_settings
from app.backend.core.errors import AppError
from app.backend.core.logging import configure_logging
from app.backend.services.job_service import JobService
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import LocalFileStorage
from app.backend.workers.job_worker import JobWorker


@dataclass
class AppState:
    storage: LocalFileStorage | None = None
    repository: JsonJobRepository | None = None
    converter: InkstitchAdapter | None = None
    worker: JobWorker | None = None
    job_service: JobService | None = None


app_state = AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    storage = LocalFileStorage(
        input_dir=settings.input_dir,
        output_dir=settings.output_dir,
        temp_dir=settings.temp_dir,
        max_file_size=settings.max_file_size,
    )
    repository = JsonJobRepository(settings.jobs_dir)
    converter = InkstitchAdapter(
        inkscape_path=settings.inkscape_path,
        extension_path=settings.inkstitch_ext_path,
        inkstitch_bin_path=settings.inkstitch_bin_path,
        timeout_seconds=settings.inkstitch_timeout_seconds,
    )
    storage.ensure_directories()
    repository.ensure_directories()
    worker = JobWorker(repository=repository, storage=storage, converter=converter)
    job_service = JobService(repository=repository, storage=storage, worker=worker)

    app_state.storage = storage
    app_state.repository = repository
    app_state.converter = converter
    app_state.worker = worker
    app_state.job_service = job_service

    worker.start()
    try:
        yield
    finally:
        worker.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": str(exc)},
    )
