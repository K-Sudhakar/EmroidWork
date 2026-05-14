import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


MAX_PIXELS = 24_000_000
MIN_LAYER_PIXELS = 18


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
        max_dimension: int = 512,
        mode: str = "color",
        threshold: int = 160,
        colors: int = 8,
        background_tolerance: int = 0,
        preserve_background: bool = False,
        turdsize: int = 8,
        opttolerance: float = 0.2,
        max_path_data_chars: int = 250_000,
        min_dimension: int = 192,
        min_colors: int = 2,
    ) -> None:
        self.imagemagick_path = imagemagick_path
        self.potrace_path = potrace_path
        self.timeout_seconds = timeout_seconds
        self.max_dimension = max_dimension
        self.mode = mode
        self.threshold = threshold
        self.colors = colors
        self.background_tolerance = background_tolerance
        self.preserve_background = preserve_background
        self.turdsize = turdsize
        self.opttolerance = opttolerance
        self.max_path_data_chars = max_path_data_chars
        self.min_dimension = min_dimension
        self.min_colors = min_colors
        self._validate_options()

    def dependency_status(self) -> tuple[bool, bool, str | None]:
        potrace_ok, potrace_detail = self._check_command([self.potrace_path, "--version"])
        return True, potrace_ok, potrace_detail

    def vectorize(self, *, input_path: Path, svg_path: Path, bitmap_path: Path) -> VectorizationResult:
        bitmap_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.parent.mkdir(parents=True, exist_ok=True)

        source = self._open_image(input_path).convert("RGBA")
        stderr = ""
        last_complexity = 0

        for profile in self._conversion_profiles():
            svg_path.unlink(missing_ok=True)
            prepared = self._resize_if_needed(source, max_dimension=profile["max_dimension"])
            prepared = self._cleanup_background(prepared.copy(), self.background_tolerance)
            rgb = self._flatten_to_white(prepared)

            with tempfile.TemporaryDirectory(
                prefix="raster-vectorizer-",
                dir=str(bitmap_path.parent),
            ) as tempdir:
                if self.mode == "bw":
                    stderr = self._convert_bw(rgb, svg_path, tempdir, profile)
                else:
                    stderr = self._convert_color(rgb, svg_path, tempdir, profile)

            last_complexity = self._svg_path_data_chars(svg_path)
            if last_complexity <= self.max_path_data_chars:
                break
        else:
            raise RasterVectorizationError(
                "Raster image produced SVG paths that are too complex for embroidery conversion.",
                stderr=(
                    f"path_data_chars={last_complexity} "
                    f"limit={self.max_path_data_chars}"
                ),
            )

        if not svg_path.exists() or svg_path.stat().st_size == 0:
            raise RasterVectorizationError("Raster vectorization did not produce an SVG.")

        bitmap_path.unlink(missing_ok=True)
        return VectorizationResult(svg_path=svg_path, stderr=stderr.strip())

    def _validate_options(self) -> None:
        if self.mode not in {"bw", "color"}:
            raise ValueError("mode must be 'bw' or 'color'")
        if not 1 <= self.colors <= 24:
            raise ValueError("colors must be between 1 and 24")
        if not 0 <= self.threshold <= 255:
            raise ValueError("threshold must be between 0 and 255")
        if self.max_dimension < 64:
            raise ValueError("max_dimension must be at least 64")
        if self.min_dimension < 64:
            raise ValueError("min_dimension must be at least 64")
        if self.min_dimension > self.max_dimension:
            raise ValueError("min_dimension cannot exceed max_dimension")
        if not 1 <= self.min_colors <= self.colors:
            raise ValueError("min_colors must be between 1 and colors")
        if self.max_path_data_chars < 1:
            raise ValueError("max_path_data_chars must be at least 1")

    def _open_image(self, path: Path) -> Image.Image:
        try:
            with Image.open(path) as probe:
                probe.verify()
            img = Image.open(path)
            img.load()
        except (OSError, UnidentifiedImageError) as exc:
            raise RasterVectorizationError("Unsupported or corrupt raster image.") from exc

        if img.width * img.height > MAX_PIXELS:
            raise RasterVectorizationError(
                "Raster image pixel count is too large.",
                stderr=f"width={img.width} height={img.height}",
            )
        return img

    def _resize_if_needed(self, img: Image.Image, *, max_dimension: int | None = None) -> Image.Image:
        max_dimension = max_dimension or self.max_dimension
        longest = max(img.size)
        if longest <= max_dimension:
            return img
        scale = max_dimension / float(longest)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        return img.resize(size, Image.Resampling.LANCZOS)

    @staticmethod
    def _corner_background(rgb: Image.Image) -> tuple[int, int, int]:
        w, h = rgb.size
        samples = [
            rgb.getpixel((0, 0)),
            rgb.getpixel((w - 1, 0)),
            rgb.getpixel((0, h - 1)),
            rgb.getpixel((w - 1, h - 1)),
        ]
        return tuple(round(sum(px[i] for px in samples) / len(samples)) for i in range(3))

    def _cleanup_background(self, rgba: Image.Image, tolerance: int) -> Image.Image:
        if tolerance <= 0:
            return rgba

        rgb = rgba.convert("RGB")
        bg = self._corner_background(rgb)
        pixels = rgba.load()
        for y in range(rgba.height):
            for x in range(rgba.width):
                r, g, b, a = pixels[x, y]
                dist = math.sqrt((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2)
                if dist <= tolerance:
                    pixels[x, y] = (255, 255, 255, 0)
        return rgba

    @staticmethod
    def _flatten_to_white(rgba: Image.Image) -> Image.Image:
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")

    @staticmethod
    def _save_pbm(mask_l: Image.Image, path: Path) -> None:
        # Potrace traces black pixels. Values <= 127 are foreground.
        bw = mask_l.point(lambda p: 0 if p <= 127 else 255, mode="1")
        bw.save(path)

    @staticmethod
    def _path_data_from_svg(svg_path: Path) -> list[str]:
        text = svg_path.read_text(encoding="utf-8", errors="ignore")
        return re.findall(r'<path[^>]*\sd="([^"]+)"[^>]*/?>', text)

    def _trace_mask(
        self,
        mask: Image.Image,
        tempdir: str,
        name: str,
        profile: dict[str, float | int],
    ) -> tuple[list[str], str]:
        pbm = Path(tempdir) / f"{name}.pbm"
        traced = Path(tempdir) / f"{name}.svg"
        self._save_pbm(mask, pbm)
        result = self._run(
            self._build_potrace_command(
                pbm,
                traced,
                turdsize=int(profile["turdsize"]),
                opttolerance=float(profile["opttolerance"]),
            ),
            "Raster vectorization failed.",
        )
        return self._path_data_from_svg(traced), result.stderr

    def _convert_bw(
        self,
        img: Image.Image,
        output: Path,
        tempdir: str,
        profile: dict[str, float | int],
    ) -> str:
        gray = ImageOps.grayscale(img)
        gray = ImageOps.autocontrast(gray)
        gray = ImageEnhance.Contrast(gray).enhance(1.15)
        mask = gray.point(lambda p: 0 if p < self.threshold else 255, mode="L")

        pbm = Path(tempdir) / "bw.pbm"
        self._save_pbm(mask, pbm)
        result = self._run(
            self._build_potrace_command(
                pbm,
                output,
                turdsize=int(profile["turdsize"]),
                opttolerance=float(profile["opttolerance"]),
            ),
            "Raster vectorization failed.",
        )
        return result.stderr

    def _convert_color(
        self,
        img: Image.Image,
        output: Path,
        tempdir: str,
        profile: dict[str, float | int],
    ) -> str:
        quantized = img.quantize(colors=int(profile["colors"]), method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette() or []
        counts = sorted(quantized.getcolors(maxcolors=int(profile["colors"]) * 4) or [], reverse=True)

        stderr_parts: list[str] = []
        layers: list[dict[str, object]] = []
        for count, index in counts:
            if count < MIN_LAYER_PIXELS:
                continue
            rgb = tuple(palette[index * 3 : index * 3 + 3])
            mask = quantized.point(lambda p, idx=index: 0 if p == idx else 255, mode="L")
            mask = mask.filter(ImageFilter.MedianFilter(size=3))
            paths, stderr = self._trace_mask(mask, tempdir, f"layer_{index}", profile)
            stderr_parts.append(stderr)
            if paths:
                layers.append({"count": count, "color": rgb, "paths": paths})

        bg = self._corner_background(img)
        if not self.preserve_background and layers:
            largest = layers[0]
            color = largest["color"]
            if isinstance(color, tuple):
                distance = math.sqrt(sum((color[i] - bg[i]) ** 2 for i in range(3)))
                coverage = int(largest["count"]) / float(img.width * img.height)
                if distance < 45 and coverage > 0.30 and self._luminance(color) > 180:
                    layers = layers[1:]

        svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{img.width}" '
                f'height="{img.height}" viewBox="0 0 {img.width} {img.height}" version="1.1">'
            ),
            '<g fill-rule="evenodd">',
        ]
        if self.preserve_background:
            svg.append(f'<rect width="100%" height="100%" fill="{self._color_hex(bg)}"/>')

        for layer in layers:
            color = layer["color"]
            paths = layer["paths"]
            if not isinstance(color, tuple) or not isinstance(paths, list):
                continue
            fill = self._color_hex(color)
            for d in paths:
                svg.append(f'<path fill="{fill}" d="{escape(d)}"/>')
        svg.extend(["</g>", "</svg>", ""])
        output.write_text("\n".join(svg), encoding="utf-8")
        return "\n".join(stderr_parts)

    @staticmethod
    def _color_hex(color: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*color[:3])

    @staticmethod
    def _luminance(color: tuple[int, int, int]) -> float:
        r, g, b = color[:3]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _conversion_profiles(self) -> list[dict[str, float | int]]:
        dimensions = [
            self.max_dimension,
            max(self.min_dimension, int(self.max_dimension * 0.75)),
            max(self.min_dimension, int(self.max_dimension * 0.5)),
            self.min_dimension,
        ]
        colors = [
            self.colors,
            max(self.min_colors, min(self.colors, 6)),
            max(self.min_colors, min(self.colors, 4)),
            self.min_colors,
        ]
        profiles: list[dict[str, float | int]] = []
        seen: set[tuple[int, int, int, float]] = set()
        for max_dimension, color_count in zip(dimensions, colors):
            profile = {
                "max_dimension": max_dimension,
                "colors": color_count,
                "turdsize": max(self.turdsize, 8 + len(profiles) * 4),
                "opttolerance": max(self.opttolerance, 0.2 + len(profiles) * 0.2),
            }
            key = (
                int(profile["max_dimension"]),
                int(profile["colors"]),
                int(profile["turdsize"]),
                float(profile["opttolerance"]),
            )
            if key in seen:
                continue
            seen.add(key)
            profiles.append(profile)
        return profiles

    def _svg_path_data_chars(self, path: Path) -> int:
        if not path.exists():
            return self.max_path_data_chars + 1
        return sum(len(d) for d in self._path_data_from_svg(path))

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
        if shutil.which(command[0]) is None:
            return False, f"Required executable not found: {command[0]}"
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

    def _build_potrace_command(
        self,
        bitmap_path: Path,
        svg_path: Path,
        *,
        turdsize: int | None = None,
        opttolerance: float | None = None,
    ) -> list[str]:
        return [
            self.potrace_path,
            str(bitmap_path),
            "--svg",
            "--flat",
            "--turdsize",
            str(turdsize if turdsize is not None else self.turdsize),
            "--opttolerance",
            str(opttolerance if opttolerance is not None else self.opttolerance),
            "-o",
            str(svg_path),
        ]

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("MAGICK_THREAD_LIMIT", "1")
        return env
