import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VectorizationResult:
    svg_path: Path
    stderr: str


class RasterVectorizationError(Exception):
    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stderr = stderr


class RasterVectorizer:
    def __init__(
        self,
        *,
        imagemagick_path: str = "convert",
        potrace_path: str = "potrace",
        timeout_seconds: int = 120,
    ) -> None:
        self.imagemagick_path = imagemagick_path
        self.potrace_path = potrace_path
        self.timeout_seconds = timeout_seconds

    def dependency_status(self) -> tuple[bool, bool, str | None]:
        imagemagick_ok, imagemagick_detail = self._check_command(
            [self.imagemagick_path, "-version"]
        )
        potrace_ok, potrace_detail = self._check_command([self.potrace_path, "--version"])
        detail = imagemagick_detail or potrace_detail
        return imagemagick_ok, potrace_ok, detail

    def vectorize(self, *, input_path: Path, svg_path: Path, bitmap_path: Path) -> VectorizationResult:
        bitmap_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_parts: list[str] = []

        convert_command = self._build_imagemagick_command(input_path, bitmap_path)
        convert_result = self._run(convert_command, "Raster preprocessing failed.")
        stderr_parts.append(convert_result.stderr)

        potrace_command = self._build_potrace_command(bitmap_path, svg_path)
        potrace_result = self._run(potrace_command, "Raster vectorization failed.")
        stderr_parts.append(potrace_result.stderr)

        if not svg_path.exists() or svg_path.stat().st_size == 0:
            raise RasterVectorizationError("Raster vectorization did not produce an SVG.")

        bitmap_path.unlink(missing_ok=True)
        return VectorizationResult(svg_path=svg_path, stderr="\n".join(stderr_parts).strip())

    def _run(self, command: list[str], failure_message: str) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr or ""
            raise RasterVectorizationError(
                f"{failure_message} Command timed out.",
                stderr=stderr,
            ) from exc
        except OSError as exc:
            raise RasterVectorizationError(f"{failure_message} {exc}") from exc

        if completed.returncode != 0:
            raise RasterVectorizationError(failure_message, stderr=completed.stderr)
        return completed

    def _check_command(self, command: list[str]) -> tuple[bool, str | None]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        if completed.returncode != 0:
            return False, completed.stderr
        return True, None

    def _build_imagemagick_command(self, input_path: Path, bitmap_path: Path) -> list[str]:
        return [
            self.imagemagick_path,
            str(input_path),
            "-alpha",
            "remove",
            "-colorspace",
            "Gray",
            "-threshold",
            "60%",
            str(bitmap_path),
        ]

    def _build_potrace_command(self, bitmap_path: Path, svg_path: Path) -> list[str]:
        return [
            self.potrace_path,
            str(bitmap_path),
            "--svg",
            "--output",
            str(svg_path),
        ]

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("MAGICK_THREAD_LIMIT", "1")
        return env
