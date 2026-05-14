from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.backend.adapters.dst_validator import DstValidator
from app.backend.adapters.inkstitch_adapter import InkstitchAdapter
from app.backend.adapters.raster_vectorizer import RasterVectorizer
from app.backend.adapters.svg_design_validator import SvgDesignValidator
from app.backend.adapters.svg_embroidery_preparer import SvgEmbroideryPreparer
from app.backend.adapters.svg_preflight import SvgPreflight
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
    vectorizer: RasterVectorizer | None = None
    design_validator: SvgDesignValidator | None = None
    embroidery_preparer: SvgEmbroideryPreparer | None = None
    svg_preflight: SvgPreflight | None = None
    dst_validator: DstValidator | None = None
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
    vectorizer = RasterVectorizer(
        imagemagick_path=settings.imagemagick_path,
        potrace_path=settings.potrace_path,
        timeout_seconds=settings.raster_vectorize_timeout_seconds,
        max_dimension=settings.raster_max_dimension,
    )
    design_validator = SvgDesignValidator(
        max_width_mm=settings.design_max_width_mm,
        max_height_mm=settings.design_max_height_mm,
        min_width_mm=settings.design_min_width_mm,
        min_height_mm=settings.design_min_height_mm,
        min_path_dimension_mm=settings.design_min_path_dimension_mm,
        max_tiny_paths=settings.design_max_tiny_paths,
    )
    embroidery_preparer = SvgEmbroideryPreparer(
        fill_row_spacing_mm=settings.embroidery_fill_row_spacing_mm,
        fill_max_stitch_length_mm=settings.embroidery_fill_max_stitch_length_mm,
        fill_underlay=settings.embroidery_fill_underlay,
        fill_underlay_inset_mm=settings.embroidery_fill_underlay_inset_mm,
        fill_underlay_row_spacing_mm=settings.embroidery_fill_underlay_row_spacing_mm,
        running_stitch_length_mm=settings.embroidery_running_stitch_length_mm,
        running_stitch_repeats=settings.embroidery_running_stitch_repeats,
        lock_stitches=settings.embroidery_lock_stitches,
    )
    svg_preflight = SvgPreflight(
        max_elements=settings.svg_preflight_max_elements,
        max_paths=settings.svg_preflight_max_paths,
        max_path_data_chars=settings.svg_preflight_max_path_data_chars,
        max_dimension=settings.svg_preflight_max_dimension,
        allow_embedded_images=settings.svg_preflight_allow_embedded_images,
    )
    dst_validator = DstValidator(
        min_stitches=settings.dst_min_stitches,
        max_stitches=settings.dst_max_stitches,
        max_width_mm=settings.design_max_width_mm,
        max_height_mm=settings.design_max_height_mm,
    )
    storage.ensure_directories()
    repository.ensure_directories()
    worker = JobWorker(
        repository=repository,
        storage=storage,
        converter=converter,
        vectorizer=vectorizer,
        design_validator=design_validator,
        embroidery_preparer=embroidery_preparer,
        svg_preflight=svg_preflight,
        dst_validator=dst_validator,
    )
    job_service = JobService(repository=repository, storage=storage, worker=worker)

    app_state.storage = storage
    app_state.repository = repository
    app_state.converter = converter
    app_state.vectorizer = vectorizer
    app_state.design_validator = design_validator
    app_state.embroidery_preparer = embroidery_preparer
    app_state.svg_preflight = svg_preflight
    app_state.dst_validator = dst_validator
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
    allow_origins=settings.cors_allowed_origins,
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
