import logging
import math
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from app.backend.core.errors import DependencyAppError
from app.backend.models.job import OutputFormat

logger = logging.getLogger(__name__)
_INVALID_ARCHIVE_PREVIEW_BYTES = 2048
_SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"
_X_DISPLAY_ERROR = "Unable to access the X Display"


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    thread_list_path: Path | None
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class InkstitchExecutionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        timed_out: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out


class InkstitchAdapter:
    def __init__(
        self,
        *,
        inkscape_path: str,
        extension_path: Path | None,
        inkstitch_bin_path: Path | None,
        timeout_seconds: int,
        max_timeout_seconds: int | None = None,
        use_xvfb: bool = False,
    ) -> None:
        self.inkscape_path = inkscape_path
        self.extension_path = extension_path
        self.inkstitch_bin_path = inkstitch_bin_path
        self.timeout_seconds = timeout_seconds
        self.max_timeout_seconds = max_timeout_seconds or timeout_seconds
        self.use_xvfb = use_xvfb

    def validate_dependencies(self) -> None:
        try:
            completed = subprocess.run(
                [self.inkscape_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DependencyAppError(
                "Inkscape is not available. Check INKSCAPE_PATH and container setup.",
                code="inkscape_unavailable",
            ) from exc
        if completed.returncode != 0:
            raise DependencyAppError(
                "Inkscape version check failed. Check INKSCAPE_PATH and container setup.",
                code="inkscape_unavailable",
            )

        if self.extension_path and not self.extension_path.exists():
            raise DependencyAppError(
                "Ink/Stitch extension path does not exist. Check INKSTITCH_EXT_PATH.",
                code="inkstitch_extension_missing",
            )

        binary = self._resolve_inkstitch_binary()
        if binary is None:
            raise DependencyAppError(
                "Ink/Stitch extension binary was not found. Check INKSTITCH_BIN_PATH or extension installation.",
                code="inkstitch_binary_missing",
            )
        if not os.access(binary, os.X_OK):
            raise DependencyAppError(
                "Ink/Stitch extension binary is not executable. Check file permissions.",
                code="inkstitch_binary_not_executable",
            )

    def dependency_status(self) -> tuple[bool, bool, str | None]:
        try:
            completed = subprocess.run(
                [self.inkscape_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, False, str(exc)
        if completed.returncode != 0:
            return False, False, completed.stderr

        if self.extension_path and not self.extension_path.exists():
            return True, False, "Ink/Stitch extension path does not exist."

        binary = self._resolve_inkstitch_binary()
        if binary is None:
            return True, False, "Ink/Stitch extension binary was not found."
        if not os.access(binary, os.X_OK):
            return True, False, "Ink/Stitch extension binary is not executable."
        return True, True, None

    def convert(
        self,
        *,
        input_path: Path,
        output_path: Path,
        output_format: OutputFormat,
        temp_zip_path: Path,
        thread_list_path: Path | None = None,
    ) -> ConversionResult:
        if output_format != OutputFormat.DST:
            raise InkstitchExecutionError(f"Unsupported output format: {output_format}")

        binary = self._resolve_inkstitch_binary()
        if binary is None:
            raise InkstitchExecutionError("Ink/Stitch extension binary was not found.")
        if not os.access(binary, os.X_OK):
            raise InkstitchExecutionError("Ink/Stitch extension binary is not executable.")

        temp_zip_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        thread_list_path = thread_list_path or output_path.with_suffix(".threadlist.txt")
        thread_list_path.parent.mkdir(parents=True, exist_ok=True)

        command = self._build_export_execution_command(binary, input_path)
        timeout_seconds = self._estimate_timeout_seconds(input_path)
        logger.info(
            "Starting Ink/Stitch conversion",
            extra={"input_path": str(input_path), "timeout_seconds": timeout_seconds},
        )

        try:
            completed = self._run_export_command(command, temp_zip_path, timeout_seconds)
            stderr = completed.stderr.decode("utf-8", errors="replace")
            if (
                completed.returncode != 0
                and not self.use_xvfb
                and _has_x_display_error(stderr)
            ):
                xvfb_command = self._build_xvfb_export_execution_command(binary, input_path)
                if xvfb_command != command:
                    temp_zip_path.unlink(missing_ok=True)
                    logger.info(
                        "Retrying Ink/Stitch conversion with Xvfb after display failure",
                        extra={"input_path": str(input_path)},
                    )
                    completed = self._run_export_command(
                        xvfb_command,
                        temp_zip_path,
                        timeout_seconds,
                    )
                    stderr = completed.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as exc:
            temp_zip_path.unlink(missing_ok=True)
            stderr = exc.stderr or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise InkstitchExecutionError(
                f"Ink/Stitch conversion timed out after {timeout_seconds} seconds.",
                stderr=stderr,
                timed_out=True,
            ) from exc
        except OSError as exc:
            raise InkstitchExecutionError(f"Failed to execute Ink/Stitch: {exc}") from exc

        if completed.returncode != 0:
            temp_zip_path.unlink(missing_ok=True)
            raise InkstitchExecutionError(
                "Ink/Stitch conversion failed.",
                stderr=stderr,
                exit_code=completed.returncode,
            )

        try:
            self._extract_format_from_zip(
                zip_path=temp_zip_path,
                output_path=output_path,
                output_format=output_format,
            )
            self._extract_optional_extension_from_zip(
                zip_path=temp_zip_path,
                output_path=thread_list_path,
                extensions=(".txt", ".threadlist"),
            )
        except InkstitchExecutionError as exc:
            temp_zip_path.unlink(missing_ok=True)
            raise InkstitchExecutionError(
                exc.message,
                stdout=exc.stdout,
                stderr=stderr,
                exit_code=completed.returncode,
            ) from exc
        if not output_path.exists() or output_path.stat().st_size == 0:
            temp_zip_path.unlink(missing_ok=True)
            raise InkstitchExecutionError(
                "Ink/Stitch completed but DST output was not generated.",
                stderr=stderr,
                exit_code=completed.returncode,
            )
        temp_zip_path.unlink(missing_ok=True)
        return ConversionResult(
            output_path=output_path,
            thread_list_path=thread_list_path if thread_list_path.exists() else None,
            stdout=f"Wrote export archive to {temp_zip_path.name}",
            stderr=stderr,
            exit_code=completed.returncode,
        )

    def _resolve_inkstitch_binary(self) -> Path | None:
        if self.inkstitch_bin_path:
            return self.inkstitch_bin_path if self.inkstitch_bin_path.is_file() else None

        if not self.extension_path or not self.extension_path.exists():
            return None

        candidates = [
            self.extension_path / "inkstitch" / "bin" / "inkstitch",
            self.extension_path / "inkstitch" / "inkstitch.py",
            self.extension_path / "bin" / "inkstitch",
            self.extension_path / "inkstitch.py",
            self.extension_path / "inkstitch",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate

        matches = sorted(
            path for path in self.extension_path.rglob("inkstitch") if path.is_file()
        )
        return matches[0] if matches else None

    @staticmethod
    def _build_zip_export_command(binary: Path, input_path: Path) -> list[str]:
        return [
            str(binary),
            "--extension=zip",
            "--format-dst=True",
            "--format-threadlist=True",
            str(input_path),
        ]

    def _build_export_execution_command(self, binary: Path, input_path: Path) -> list[str]:
        command = self._build_zip_export_command(binary, input_path)
        if not self.use_xvfb or shutil.which("xvfb-run") is None:
            return command
        return self._build_xvfb_export_execution_command(binary, input_path)

    def _build_xvfb_export_execution_command(
        self,
        binary: Path,
        input_path: Path,
    ) -> list[str]:
        command = self._build_zip_export_command(binary, input_path)
        if shutil.which("xvfb-run") is None:
            return command
        return [
            "xvfb-run",
            "--auto-servernum",
            "--server-args=-screen 0 1024x768x24",
            *command,
        ]

    def _run_export_command(
        self,
        command: list[str],
        temp_zip_path: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[bytes]:
        with temp_zip_path.open("wb") as zip_output:
            return subprocess.run(
                command,
                stdout=zip_output,
                stderr=subprocess.PIPE,
                text=False,
                timeout=timeout_seconds,
                check=False,
                env=self._subprocess_env(),
            )

    def _estimate_timeout_seconds(self, input_path: Path) -> int:
        max_timeout = max(self.timeout_seconds, self.max_timeout_seconds)
        try:
            file_size = input_path.stat().st_size
            root = ET.parse(input_path).getroot()
        except (OSError, ET.ParseError):
            return self.timeout_seconds

        path_count = 0
        path_data_chars = 0
        for element in root.iter():
            if _local_name(element.tag) != "path":
                continue
            path_count += 1
            path_data_chars += len(element.attrib.get("d", ""))

        extra_seconds = (
            math.ceil(max(0, path_count - 250) / 250) * 60
            + math.ceil(max(0, path_data_chars - 100_000) / 100_000) * 60
            + math.ceil(max(0, file_size - 1_000_000) / 1_000_000) * 30
        )
        return min(max_timeout, self.timeout_seconds + extra_seconds)

    @staticmethod
    def _extract_format_from_zip(
        *,
        zip_path: Path,
        output_path: Path,
        output_format: OutputFormat,
    ) -> None:
        extension = f".{output_format.value.lower()}"
        if not zipfile.is_zipfile(zip_path):
            raise InkstitchExecutionError(
                "Ink/Stitch did not return a valid zip export archive.",
                stdout=_preview_file(zip_path),
            )
        try:
            with zipfile.ZipFile(zip_path) as archive:
                match = next(
                    (
                        name
                        for name in archive.namelist()
                        if name.lower().endswith(extension)
                    ),
                    None,
                )
                if match is None:
                    raise InkstitchExecutionError(
                        f"Ink/Stitch archive did not contain a {extension} file."
                    )
                with archive.open(match) as source, output_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        except zipfile.BadZipFile as exc:
            raise InkstitchExecutionError(
                "Ink/Stitch did not return a valid zip export archive.",
                stdout=_preview_file(zip_path),
            ) from exc

    @staticmethod
    def _extract_optional_extension_from_zip(
        *,
        zip_path: Path,
        output_path: Path,
        extensions: tuple[str, ...],
    ) -> bool:
        if not zipfile.is_zipfile(zip_path):
            return False
        try:
            with zipfile.ZipFile(zip_path) as archive:
                match = next(
                    (
                        name
                        for name in archive.namelist()
                        if name.lower().endswith(extensions)
                    ),
                    None,
                )
                if match is None:
                    return False
                with archive.open(match) as source, output_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                return output_path.exists() and output_path.stat().st_size > 0
        except zipfile.BadZipFile:
            return False

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("GDK_BACKEND", "x11")
        return env


def _preview_file(path: Path) -> str:
    try:
        data = path.read_bytes()[:_INVALID_ARCHIVE_PREVIEW_BYTES]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace").strip()


def _local_name(tag: str) -> str:
    if tag.startswith(_SVG_NAMESPACE):
        return tag.removeprefix(_SVG_NAMESPACE)
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _has_x_display_error(stderr: str) -> bool:
    return _X_DISPLAY_ERROR.lower() in stderr.lower()
