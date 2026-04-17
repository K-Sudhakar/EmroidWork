import logging
import queue
import threading
from pathlib import Path

from app.backend.adapters.inkstitch_adapter import InkstitchAdapter, InkstitchExecutionError
from app.backend.adapters.raster_vectorizer import RasterVectorizationError, RasterVectorizer
from app.backend.models.job import InputFormat, JobStatus
from app.backend.storage.job_repository import JsonJobRepository
from app.backend.storage.local import LocalFileStorage

logger = logging.getLogger(__name__)

_MAX_ERROR_DETAIL_LENGTH = 700


class JobWorker:
    def __init__(
        self,
        *,
        repository: JsonJobRepository,
        storage: LocalFileStorage,
        converter: InkstitchAdapter,
        vectorizer: RasterVectorizer,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.converter = converter
        self.vectorizer = vectorizer
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._thread.start()
        logger.info("Job worker started")

    def stop(self) -> None:
        self._stop_event.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Job worker stopped")

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                break
            try:
                self._process(job_id)
            except Exception:
                logger.exception("Unexpected worker failure", extra={"job_id": job_id})
            finally:
                self._queue.task_done()

    def _process(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        try:
            logger.info("Job validation started", extra={"job_id": job_id})
            job = self.repository.update(job.with_status(JobStatus.VALIDATING))
            self.storage.validate_input_file(job.input_path, job.input_format)

            output_path = self.storage.output_path_for(job.job_id, job.output_format.value)
            temp_zip_path = self.storage.temp_path_for(job.job_id, f"{job.job_id}.zip")
            conversion_input_path = self._prepare_conversion_input(job_id)

            job = self.repository.update(job.with_status(JobStatus.PROCESSING))
            result = self.converter.convert(
                input_path=conversion_input_path,
                output_path=output_path,
                output_format=job.output_format,
                temp_zip_path=temp_zip_path,
            )
            self.repository.update(
                job.with_status(JobStatus.COMPLETED, output_path=result.output_path)
            )
            logger.info("Job completed", extra={"job_id": job_id})
        except InkstitchExecutionError as exc:
            logger.error(
                "Job conversion failed",
                extra={
                    "job_id": job_id,
                    "exit_code": exc.exit_code,
                    "timed_out": exc.timed_out,
                    "stderr": exc.stderr[:1000],
                },
            )
            self.repository.update(
                job.with_status(
                    JobStatus.FAILED,
                    error_message=_format_conversion_error(exc),
                )
            )
        except RasterVectorizationError as exc:
            logger.error(
                "Job raster vectorization failed",
                extra={"job_id": job_id, "stderr": exc.stderr[:1000]},
            )
            self.repository.update(
                job.with_status(
                    JobStatus.FAILED,
                    error_message=_format_vectorization_error(exc),
                )
            )
        except Exception:
            logger.exception("Job failed", extra={"job_id": job_id})
            self.repository.update(
                job.with_status(JobStatus.FAILED, error_message="Job processing failed.")
            )
        finally:
            self.storage.cleanup_temp(job_id)

    def _prepare_conversion_input(self, job_id: str) -> Path:
        job = self.repository.get(job_id)
        if job.input_format == InputFormat.SVG:
            return job.input_path

        svg_path = self.storage.temp_path_for(job_id, f"{job_id}.svg")
        bitmap_path = self.storage.temp_path_for(job_id, f"{job_id}.pbm")
        result = self.vectorizer.vectorize(
            input_path=job.input_path,
            svg_path=svg_path,
            bitmap_path=bitmap_path,
        )
        self.storage.validate_svg_file(result.svg_path)
        return result.svg_path


def _format_conversion_error(exc: InkstitchExecutionError) -> str:
    detail = " ".join((exc.stderr or "").split())
    if not detail:
        return exc.message
    if len(detail) > _MAX_ERROR_DETAIL_LENGTH:
        detail = f"{detail[:_MAX_ERROR_DETAIL_LENGTH]}..."
    return f"{exc.message} Detail: {detail}"


def _format_vectorization_error(exc: RasterVectorizationError) -> str:
    detail = " ".join((exc.stderr or "").split())
    if not detail:
        return exc.message
    if len(detail) > _MAX_ERROR_DETAIL_LENGTH:
        detail = f"{detail[:_MAX_ERROR_DETAIL_LENGTH]}..."
    return f"{exc.message} Detail: {detail}"
