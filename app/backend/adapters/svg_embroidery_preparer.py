import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


INKSTITCH_NAMESPACE = "http://inkstitch.org/namespace"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_INKSTITCH_ATTR_PREFIX = f"{{{INKSTITCH_NAMESPACE}}}"
_INKSCAPE_NORMALIZE_TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbroideryPreparationResult:
    svg_path: Path
    fill_paths: int
    stroke_paths: int
    converted_with_inkscape: bool


class SvgEmbroideryPreparationError(Exception):
    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stderr = stderr


class SvgEmbroideryPreparer:
    def __init__(
        self,
        *,
        inkscape_path: str | None = None,
        normalize_with_inkscape: bool = False,
        fill_row_spacing_mm: float = 0.4,
        fill_max_stitch_length_mm: float = 4.0,
        fill_underlay: bool = True,
        fill_underlay_inset_mm: float = 0.4,
        fill_underlay_row_spacing_mm: float = 3.0,
        running_stitch_length_mm: float = 2.5,
        running_stitch_repeats: int = 1,
        lock_stitches: bool = True,
    ) -> None:
        self.inkscape_path = inkscape_path
        self.normalize_with_inkscape = normalize_with_inkscape
        self.fill_row_spacing_mm = fill_row_spacing_mm
        self.fill_max_stitch_length_mm = fill_max_stitch_length_mm
        self.fill_underlay = fill_underlay
        self.fill_underlay_inset_mm = fill_underlay_inset_mm
        self.fill_underlay_row_spacing_mm = fill_underlay_row_spacing_mm
        self.running_stitch_length_mm = running_stitch_length_mm
        self.running_stitch_repeats = running_stitch_repeats
        self.lock_stitches = lock_stitches

    def prepare(self, *, input_path: Path, output_path: Path) -> EmbroideryPreparationResult:
        ElementTree.register_namespace("", SVG_NAMESPACE)
        ElementTree.register_namespace("inkstitch", INKSTITCH_NAMESPACE)

        converted_with_inkscape = False
        parse_path = input_path
        if self.normalize_with_inkscape and self.inkscape_path:
            self._normalize_svg_with_inkscape(input_path=input_path, output_path=output_path)
            parse_path = output_path
            converted_with_inkscape = True

        try:
            tree = ElementTree.parse(parse_path)
        except ElementTree.ParseError as exc:
            raise SvgEmbroideryPreparationError(
                "Prepared SVG is not well-formed XML after path normalization."
            ) from exc
        root = tree.getroot()
        fill_paths = 0
        stroke_paths = 0

        for element in root.iter():
            if _local_name(element.tag) != "path":
                continue
            style = _parse_style(element.attrib.get("style", ""))
            if _has_fill(element, style):
                self._apply_fill_parameters(element)
                fill_paths += 1
            if _has_stroke(element, style):
                self._apply_stroke_parameters(element)
                stroke_paths += 1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        return EmbroideryPreparationResult(
            svg_path=output_path,
            fill_paths=fill_paths,
            stroke_paths=stroke_paths,
            converted_with_inkscape=converted_with_inkscape,
        )

    def _apply_fill_parameters(self, element: ElementTree.Element) -> None:
        _setdefault_inkstitch_attr(element, "auto_fill", "true")
        _setdefault_inkstitch_attr(
            element,
            "row_spacing_mm",
            _format_number(self.fill_row_spacing_mm),
        )
        _setdefault_inkstitch_attr(
            element,
            "max_stitch_length_mm",
            _format_number(self.fill_max_stitch_length_mm),
        )
        _setdefault_inkstitch_attr(element, "fill_underlay", _format_bool(self.fill_underlay))
        if self.fill_underlay:
            _setdefault_inkstitch_attr(
                element,
                "fill_underlay_inset_mm",
                _format_number(self.fill_underlay_inset_mm),
            )
            _setdefault_inkstitch_attr(
                element,
                "fill_underlay_row_spacing_mm",
                _format_number(self.fill_underlay_row_spacing_mm),
            )
            _setdefault_inkstitch_attr(
                element,
                "fill_underlay_max_stitch_length_mm",
                _format_number(self.fill_max_stitch_length_mm),
            )
        _setdefault_inkstitch_attr(element, "ties", _format_bool(self.lock_stitches))

    def _apply_stroke_parameters(self, element: ElementTree.Element) -> None:
        _setdefault_inkstitch_attr(
            element,
            "running_stitch_length_mm",
            _format_number(self.running_stitch_length_mm),
        )
        _setdefault_inkstitch_attr(
            element,
            "repeats",
            str(self.running_stitch_repeats),
        )
        _setdefault_inkstitch_attr(element, "ties", _format_bool(self.lock_stitches))

    def _normalize_svg_with_inkscape(self, *, input_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.inkscape_path or "inkscape",
            "--batch-process",
            f"--actions=select-all:all;object-to-path;object-stroke-to-path;vacuum-defs;export-filename:{output_path};export-plain-svg;export-do",
            str(input_path),
        ]
        logger.info(
            "Normalizing SVG paths with Inkscape",
            extra={"input_path": str(input_path), "output_path": str(output_path)},
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=_INKSCAPE_NORMALIZE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SvgEmbroideryPreparationError(
                "Inkscape SVG path normalization timed out.",
                stderr=(exc.stderr or ""),
            ) from exc
        except OSError as exc:
            raise SvgEmbroideryPreparationError(
                "Inkscape is not available for SVG path normalization. Check INKSCAPE_PATH.",
                stderr=str(exc),
            ) from exc

        if completed.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise SvgEmbroideryPreparationError(
                "Inkscape failed to normalize SVG objects to paths.",
                stderr=completed.stderr,
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise SvgEmbroideryPreparationError(
                "Inkscape path normalization did not generate an SVG output.",
                stderr=completed.stderr,
            )


def _setdefault_inkstitch_attr(
    element: ElementTree.Element,
    name: str,
    value: str,
) -> None:
    element.attrib.setdefault(f"{_INKSTITCH_ATTR_PREFIX}{name}", value)


def _has_fill(element: ElementTree.Element, style: dict[str, str]) -> bool:
    fill = _style_or_attr(element, style, "fill")
    fill_opacity = _style_or_attr(element, style, "fill-opacity")
    opacity = _style_or_attr(element, style, "opacity")
    if _is_zero_opacity(fill_opacity) or _is_zero_opacity(opacity):
        return False
    if fill is None:
        return _path_is_closed(element.attrib.get("d", ""))
    return fill.strip().lower() not in {"none", "transparent"}


def _has_stroke(element: ElementTree.Element, style: dict[str, str]) -> bool:
    stroke = _style_or_attr(element, style, "stroke")
    stroke_opacity = _style_or_attr(element, style, "stroke-opacity")
    opacity = _style_or_attr(element, style, "opacity")
    if _is_zero_opacity(stroke_opacity) or _is_zero_opacity(opacity):
        return False
    return stroke is not None and stroke.strip().lower() not in {"none", "transparent"}


def _style_or_attr(
    element: ElementTree.Element,
    style: dict[str, str],
    name: str,
) -> str | None:
    return style.get(name, element.attrib.get(name))


def _parse_style(value: str) -> dict[str, str]:
    declarations = {}
    for item in value.split(";"):
        name, separator, declaration_value = item.partition(":")
        if not separator:
            continue
        declarations[name.strip().lower()] = declaration_value.strip()
    return declarations


def _is_zero_opacity(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return float(value) <= 0
    except ValueError:
        return False


def _local_name(tag: str) -> str:
    return tag.split("}")[-1].lower()


def _path_is_closed(path_data: str) -> bool:
    return path_data.rstrip().lower().endswith("z")


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_number(value: float) -> str:
    return f"{value:g}"
