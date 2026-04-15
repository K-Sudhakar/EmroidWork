import logging
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.backend.core.errors import DependencyAppError
from app.backend.models.job import OutputFormat

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
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
    ) -> None:
        self.inkscape_path = inkscape_path
        self.extension_path = extension_path
        self.inkstitch_bin_path = inkstitch_bin_path
        self.timeout_seconds = timeout_seconds

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

        command = self._build_zip_export_command(binary, input_path)
        logger.info("Starting Ink/Stitch conversion", extra={"input_path": str(input_path)})

        try:
            with temp_zip_path.open("wb") as zip_output:
                completed = subprocess.run(
                    command,
                    stdout=zip_output,
                    stderr=subprocess.PIPE,
                    text=False,
                    timeout=self.timeout_seconds,
                    check=False,
                    env=self._subprocess_env(),
                )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise InkstitchExecutionError(
                "Ink/Stitch conversion timed out.",
                stderr=stderr,
                timed_out=True,
            ) from exc
        except OSError as exc:
            raise InkstitchExecutionError(f"Failed to execute Ink/Stitch: {exc}") from exc

        stderr = completed.stderr.decode("utf-8", errors="replace")
        if completed.returncode != 0:
            temp_zip_path.unlink(missing_ok=True)
            raise InkstitchExecutionError(
                "Ink/Stitch conversion failed.",
                stderr=stderr,
                exit_code=completed.returncode,
            )

        self._extract_format_from_zip(
            zip_path=temp_zip_path,
            output_path=output_path,
            output_format=output_format,
        )
        temp_zip_path.unlink(missing_ok=True)
        return ConversionResult(
            output_path=output_path,
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
            str(input_path),
        ]

    @staticmethod
    def _extract_format_from_zip(
        *,
        zip_path: Path,
        output_path: Path,
        output_format: OutputFormat,
    ) -> None:
        extension = f".{output_format.value.lower()}"
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
                "Ink/Stitch did not return a valid zip export archive."
            ) from exc

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("GDK_BACKEND", "x11")
        return env
