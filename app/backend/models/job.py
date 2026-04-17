from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OutputFormat(StrEnum):
    DST = "dst"
    PES = "pes"


class InputFormat(StrEnum):
    SVG = "svg"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"


SUPPORTED_OUTPUT_FORMATS = {OutputFormat.DST}
SUPPORTED_INPUT_FORMATS = {
    InputFormat.SVG,
    InputFormat.PNG,
    InputFormat.JPG,
    InputFormat.JPEG,
}


class Job(BaseModel):
    job_id: str
    filename: str
    input_path: Path
    input_format: InputFormat = InputFormat.SVG
    output_path: Path | None = None
    output_format: OutputFormat
    status: JobStatus = JobStatus.RECEIVED
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def with_status(
        self,
        status: JobStatus,
        *,
        output_path: Path | None = None,
        error_message: str | None = None,
    ) -> "Job":
        update = {
            "status": status,
            "updated_at": datetime.now(UTC),
            "error_message": error_message,
        }
        if output_path is not None:
            update["output_path"] = output_path
        return self.model_copy(update=update)
