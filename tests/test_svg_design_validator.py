import pytest

from app.backend.adapters.svg_design_validator import (
    SvgDesignValidationError,
    SvgDesignValidator,
)


def test_svg_design_validator_accepts_viewbox_sized_design(tmp_path):
    path = tmp_path / "input.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        '<path d="M0 0 H20 V20 Z"/>'
        "</svg>",
        encoding="utf-8",
    )

    report = SvgDesignValidator(max_width_mm=30, max_height_mm=30).validate(path)

    assert round(report.width_mm, 2) == 25.4
    assert round(report.height_mm, 2) == 25.4


def test_svg_design_validator_rejects_oversized_design(tmp_path):
    path = tmp_path / "input.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="150mm" height="80mm"/>',
        encoding="utf-8",
    )

    with pytest.raises(SvgDesignValidationError, match="exceeds the configured hoop width"):
        SvgDesignValidator(max_width_mm=100, max_height_mm=100).validate(path)


def test_svg_design_validator_rejects_missing_size(tmp_path):
    path = tmp_path / "input.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")

    with pytest.raises(SvgDesignValidationError, match="must define width/height or viewBox"):
        SvgDesignValidator().validate(path)


def test_svg_design_validator_rejects_too_many_tiny_paths(tmp_path):
    path = tmp_path / "input.svg"
    tiny_paths = "".join(
        '<path d="M0 0 H1 V1 Z"/>' for _index in range(3)
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm">{tiny_paths}</svg>',
        encoding="utf-8",
    )

    with pytest.raises(SvgDesignValidationError, match="too many paths"):
        SvgDesignValidator(min_path_dimension_mm=0.5, max_tiny_paths=2).validate(path)
