import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_LENGTH_PATTERN = re.compile(
    r"^\s*(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>[A-Za-z%]*)"
)


@dataclass(frozen=True)
class SvgDesignValidationReport:
    width_mm: float | None
    height_mm: float | None
    tiny_path_count: int


class SvgDesignValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SvgDesignValidator:
    def __init__(
        self,
        *,
        max_width_mm: float = 100,
        max_height_mm: float = 100,
        min_width_mm: float = 1,
        min_height_mm: float = 1,
        min_path_dimension_mm: float = 0.4,
        max_tiny_paths: int = 20,
    ) -> None:
        self.max_width_mm = max_width_mm
        self.max_height_mm = max_height_mm
        self.min_width_mm = min_width_mm
        self.min_height_mm = min_height_mm
        self.min_path_dimension_mm = min_path_dimension_mm
        self.max_tiny_paths = max_tiny_paths

    def validate(self, path: Path) -> SvgDesignValidationReport:
        try:
            root = ElementTree.parse(path).getroot()
        except ElementTree.ParseError as exc:
            raise SvgDesignValidationError("Uploaded file is not well-formed XML/SVG.") from exc

        if _local_name(root.tag) != "svg":
            raise SvgDesignValidationError("Uploaded file is not a valid SVG document.")

        width_mm, height_mm = self._dimensions_mm(root)
        self._validate_dimensions(width_mm, height_mm)
        tiny_path_count = self._count_tiny_paths(root)
        if tiny_path_count > self.max_tiny_paths:
            raise SvgDesignValidationError(
                "SVG contains too many paths below the stitchable size threshold: "
                f"{tiny_path_count} paths are smaller than {self.min_path_dimension_mm:g} mm."
            )
        return SvgDesignValidationReport(
            width_mm=width_mm,
            height_mm=height_mm,
            tiny_path_count=tiny_path_count,
        )

    def _dimensions_mm(self, root: ElementTree.Element) -> tuple[float | None, float | None]:
        width_mm = _parse_length_mm(root.attrib.get("width"))
        height_mm = _parse_length_mm(root.attrib.get("height"))
        if width_mm is not None and height_mm is not None:
            return width_mm, height_mm

        view_box = _parse_view_box(root.attrib.get("viewBox"))
        if view_box is None:
            return width_mm, height_mm
        _min_x, _min_y, view_box_width, view_box_height = view_box
        return width_mm or _px_to_mm(view_box_width), height_mm or _px_to_mm(view_box_height)

    def _validate_dimensions(self, width_mm: float | None, height_mm: float | None) -> None:
        if width_mm is None or height_mm is None:
            raise SvgDesignValidationError(
                "SVG must define width/height or viewBox so embroidery size can be validated."
            )
        if width_mm > self.max_width_mm:
            raise SvgDesignValidationError(
                f"Design width {width_mm:g} mm exceeds the configured hoop width "
                f"limit of {self.max_width_mm:g} mm."
            )
        if height_mm > self.max_height_mm:
            raise SvgDesignValidationError(
                f"Design height {height_mm:g} mm exceeds the configured hoop height "
                f"limit of {self.max_height_mm:g} mm."
            )
        if width_mm < self.min_width_mm:
            raise SvgDesignValidationError(
                f"Design width {width_mm:g} mm is below the minimum stitchable width "
                f"of {self.min_width_mm:g} mm."
            )
        if height_mm < self.min_height_mm:
            raise SvgDesignValidationError(
                f"Design height {height_mm:g} mm is below the minimum stitchable height "
                f"of {self.min_height_mm:g} mm."
            )

    def _count_tiny_paths(self, root: ElementTree.Element) -> int:
        tiny_paths = 0
        for element in root.iter():
            if _local_name(element.tag) != "path":
                continue
            bounds = _path_coordinate_bounds(element.attrib.get("d", ""))
            if bounds is None:
                continue
            min_x, min_y, max_x, max_y = bounds
            width_mm = _px_to_mm(max_x - min_x)
            height_mm = _px_to_mm(max_y - min_y)
            if width_mm < self.min_path_dimension_mm or height_mm < self.min_path_dimension_mm:
                tiny_paths += 1
        return tiny_paths


def _parse_length_mm(value: str | None) -> float | None:
    if value is None:
        return None
    match = _LENGTH_PATTERN.match(value)
    if not match:
        return None
    number = float(match.group("value"))
    unit = match.group("unit").lower()
    if unit in {"", "px"}:
        return _px_to_mm(number)
    if unit == "mm":
        return number
    if unit == "cm":
        return number * 10
    if unit == "in":
        return number * 25.4
    if unit == "pt":
        return number * 25.4 / 72
    if unit == "pc":
        return number * 25.4 / 6
    return None


def _parse_view_box(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    numbers = [float(match.group(0)) for match in _NUMBER_PATTERN.finditer(value)]
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _path_coordinate_bounds(path_data: str) -> tuple[float, float, float, float] | None:
    numbers = [float(match.group(0)) for match in _NUMBER_PATTERN.finditer(path_data)]
    if len(numbers) < 2:
        return None
    xs = numbers[0::2]
    ys = numbers[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def _px_to_mm(value: float) -> float:
    return value * 25.4 / 96


def _local_name(tag: str) -> str:
    return tag.split("}")[-1].lower()
