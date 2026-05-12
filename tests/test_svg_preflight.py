import pytest

from app.backend.adapters.svg_preflight import SvgPreflight, SvgPreflightError


def write_svg(tmp_path, content: str):
    path = tmp_path / "input.svg"
    path.write_text(content, encoding="utf-8")
    return path


def test_preflight_accepts_simple_svg(tmp_path):
    path = write_svg(
        tmp_path,
        '<svg width="100" height="50" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M 0 0 L 10 10"/></svg>',
    )

    report = SvgPreflight().validate(path)

    assert report.element_count == 2
    assert report.path_count == 1
    assert report.path_data_chars == 13
    assert report.width == 100
    assert report.height == 50


def test_preflight_rejects_too_many_elements(tmp_path):
    path = write_svg(tmp_path, "<svg><g/><g/><g/></svg>")

    with pytest.raises(SvgPreflightError, match="4 elements exceeds the limit of 3"):
        SvgPreflight(max_elements=3).validate(path)


def test_preflight_rejects_too_many_paths(tmp_path):
    path = write_svg(tmp_path, '<svg><path d="M0 0"/><path d="M1 1"/></svg>')

    with pytest.raises(SvgPreflightError, match="2 paths exceeds the limit of 1"):
        SvgPreflight(max_paths=1).validate(path)


def test_preflight_rejects_large_path_data(tmp_path):
    path = write_svg(tmp_path, f'<svg><path d="{"M0 0 " * 20}"/></svg>')

    with pytest.raises(SvgPreflightError, match="exceeds the limit of 10"):
        SvgPreflight(max_path_data_chars=10).validate(path)


def test_preflight_rejects_oversized_dimensions(tmp_path):
    path = write_svg(tmp_path, '<svg width="10001px" height="20"></svg>')

    with pytest.raises(SvgPreflightError, match="SVG width is too large"):
        SvgPreflight(max_dimension=10000).validate(path)


def test_preflight_rejects_embedded_images(tmp_path):
    path = write_svg(tmp_path, '<svg><image href="data:image/png;base64,abcd"/></svg>')

    with pytest.raises(SvgPreflightError, match="embedded raster images"):
        SvgPreflight().validate(path)


def test_preflight_can_allow_embedded_images(tmp_path):
    path = write_svg(tmp_path, '<svg><image href="data:image/png;base64,abcd"/></svg>')

    report = SvgPreflight(allow_embedded_images=True).validate(path)

    assert report.has_embedded_image is True
