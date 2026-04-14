import re
import shutil
from pathlib import Path
from xml.etree import ElementTree

from starlette.datastructures import UploadFile

from app.backend.core.errors import ValidationAppError

_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_SVG_CONTENT_TYPES = {
    "image/svg+xml",
    "application/svg+xml",
    "text/xml",
    "application/xml",
    "application/octet-stream",
}


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "upload.svg").name.strip()
    name = _SAFE_FILENAME_PATTERN.sub("_", name)
    name = name.strip("._")
    if not name:
        name = "upload.svg"
    if len(name) > 120:
        stem = Path(name).stem[:100]
        suffix = Path(name).suffix[:20]
        name = f"{stem}{suffix}"
    return name


class LocalFileStorage:
    def __init__(
        self,
        *,
        input_dir: Path,
        output_dir: Path,
        temp_dir: Path,
        max_file_size: int,
    ) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.max_file_size = max_file_size

    def ensure_directories(self) -> None:
        for directory in (self.input_dir, self.output_dir, self.temp_dir):
            directory.mkdir(parents=True, exist_ok=True)

    async def save_svg_upload(self, job_id: str, upload: UploadFile) -> tuple[str, Path]:
        self._validate_upload_metadata(upload)
        filename = sanitize_filename(upload.filename or "upload.svg")
        if Path(filename).suffix.lower() != ".svg":
            raise ValidationAppError("Only SVG files are supported.", code="invalid_file_type")

        job_dir = self.input_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        destination = job_dir / filename

        size = 0
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_file_size:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise ValidationAppError(
                        "Uploaded file exceeds the configured size limit.",
                        code="file_too_large",
                    )
                output.write(chunk)

        if size == 0:
            destination.unlink(missing_ok=True)
            raise ValidationAppError("Uploaded SVG file is empty.", code="empty_file")

        self.validate_svg_file(destination)
        return filename, destination

    def output_path_for(self, job_id: str, output_format: str) -> Path:
        output_dir = self.output_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{job_id}.{output_format.lower()}"

    def temp_path_for(self, job_id: str, filename: str) -> Path:
        temp_dir = self.temp_dir / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir / sanitize_filename(filename)

    def cleanup_temp(self, job_id: str) -> None:
        shutil.rmtree(self.temp_dir / job_id, ignore_errors=True)

    def validate_svg_file(self, path: Path) -> None:
        try:
            for _event, element in ElementTree.iterparse(path, events=("start",)):
                if element.tag.split("}")[-1].lower() != "svg":
                    raise ValidationAppError(
                        "Uploaded file is not a valid SVG document.",
                        code="invalid_svg",
                    )
                return
        except ElementTree.ParseError as exc:
            raise ValidationAppError(
                "Uploaded file is not well-formed XML/SVG.",
                code="invalid_svg",
            ) from exc

    @staticmethod
    def _validate_upload_metadata(upload: UploadFile) -> None:
        content_type = (upload.content_type or "").split(";")[0].strip().lower()
        if content_type and content_type not in _SVG_CONTENT_TYPES:
            raise ValidationAppError(
                "Only SVG uploads are accepted.",
                code="invalid_content_type",
            )
