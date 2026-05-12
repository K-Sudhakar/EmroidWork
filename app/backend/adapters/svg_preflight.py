from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


class SvgPreflightError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class SvgPreflightReport:
    element_count: int
    path_count: int
    path_data_chars: int
    width: float | None
    height: float | None
    has_embedded_image: bool


class SvgPreflight:
    def __init__(
        self,
        *,
        max_elements: int = 5000,
        max_paths: int = 2000,
        max_path_data_chars: int = 250000,
        max_dimension: int = 10000,
        allow_embedded_images: bool = False,
    ) -> None:
        self.max_elements = max_elements
        self.max_paths = max_paths
        self.max_path_data_chars = max_path_data_chars
        self.max_dimension = max_dimension
        self.allow_embedded_images = allow_embedded_images

    def validate(self, path: Path) -> SvgPreflightReport:
        report = self.inspect(path)
        if report.element_count > self.max_elements:
            raise SvgPreflightError(
                "SVG is too complex for conversion: "
                f"{report.element_count} elements exceeds the limit of {self.max_elements}."
            )
        if report.path_count > self.max_paths:
            raise SvgPreflightError(
                "SVG is too complex for conversion: "
                f"{report.path_count} paths exceeds the limit of {self.max_paths}."
            )
        if report.path_data_chars > self.max_path_data_chars:
            raise SvgPreflightError(
                "SVG path data is too complex for conversion: "
                f"{report.path_data_chars} characters exceeds the limit of {self.max_path_data_chars}."
            )
        if self._dimension_exceeds_limit(report.width):
            raise SvgPreflightError(
                "SVG width is too large for conversion: "
                f"{report.width:g} exceeds the limit of {self.max_dimension}."
            )
        if self._dimension_exceeds_limit(report.height):
            raise SvgPreflightError(
                "SVG height is too large for conversion: "
                f"{report.height:g} exceeds the limit of {self.max_dimension}."
            )
        if report.has_embedded_image and not self.allow_embedded_images:
            raise SvgPreflightError(
                "SVG contains embedded raster images. Upload the raster image directly or "
                "convert it to clean vector paths before requesting embroidery conversion."
            )
        return report

    def inspect(self, path: Path) -> SvgPreflightReport:
        element_count = 0
        path_count = 0
        path_data_chars = 0
        width: float | None = None
        height: float | None = None
        has_embedded_image = False

        try:
            for _event, element in ElementTree.iterparse(path, events=("start",)):
                element_count += 1
                tag = _local_name(element.tag)
                if element_count == 1:
                    if tag != "svg":
                        raise SvgPreflightError("Uploaded file is not a valid SVG document.")
                    width = _parse_svg_number(element.attrib.get("width"))
                    height = _parse_svg_number(element.attrib.get("height"))

                if tag == "path":
                    path_count += 1
                    path_data_chars += len(element.attrib.get("d", ""))
                elif tag == "image":
                    has_embedded_image = True
        except ElementTree.ParseError as exc:
            raise SvgPreflightError("Uploaded file is not well-formed XML/SVG.") from exc

        return SvgPreflightReport(
            element_count=element_count,
            path_count=path_count,
            path_data_chars=path_data_chars,
            width=width,
            height=height,
            has_embedded_image=has_embedded_image,
        )

    def _dimension_exceeds_limit(self, value: float | None) -> bool:
        return value is not None and value > self.max_dimension


def _local_name(tag: str) -> str:
    return tag.split("}")[-1].lower()


def _parse_svg_number(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip()
    numeric = []
    for index, character in enumerate(stripped):
        if character.isdigit() or character in {".", "+", "-"}:
            numeric.append(character)
            continue
        if character in {"e", "E"} and index > 0:
            numeric.append(character)
            continue
        break
    if not numeric:
        return None
    try:
        return float("".join(numeric))
    except ValueError:
        return None
