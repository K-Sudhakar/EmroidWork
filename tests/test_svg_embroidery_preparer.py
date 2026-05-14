from xml.etree import ElementTree

from app.backend.adapters.svg_embroidery_preparer import (
    INKSTITCH_NAMESPACE,
    SvgEmbroideryPreparer,
)


INK = f"{{{INKSTITCH_NAMESPACE}}}"


def test_prepare_adds_inkstitch_fill_parameters(tmp_path):
    input_path = tmp_path / "input.svg"
    output_path = tmp_path / "prepared.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 H10 V10 Z" fill="#000000"/>'
        "</svg>",
        encoding="utf-8",
    )

    result = SvgEmbroideryPreparer().prepare(
        input_path=input_path,
        output_path=output_path,
    )

    root = ElementTree.parse(output_path).getroot()
    path = next(root.iter("{http://www.w3.org/2000/svg}path"))
    assert result.fill_paths == 1
    assert result.stroke_paths == 0
    assert path.attrib[f"{INK}auto_fill"] == "true"
    assert path.attrib[f"{INK}row_spacing_mm"] == "0.4"
    assert path.attrib[f"{INK}fill_underlay"] == "true"
    assert path.attrib[f"{INK}ties"] == "true"


def test_prepare_adds_running_stitch_parameters_for_strokes(tmp_path):
    input_path = tmp_path / "input.svg"
    output_path = tmp_path / "prepared.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 H10" fill="none" stroke="black"/>'
        "</svg>",
        encoding="utf-8",
    )

    result = SvgEmbroideryPreparer().prepare(
        input_path=input_path,
        output_path=output_path,
    )

    root = ElementTree.parse(output_path).getroot()
    path = next(root.iter("{http://www.w3.org/2000/svg}path"))
    assert result.fill_paths == 0
    assert result.stroke_paths == 1
    assert path.attrib[f"{INK}running_stitch_length_mm"] == "2.5"
    assert path.attrib[f"{INK}repeats"] == "1"
    assert path.attrib[f"{INK}ties"] == "true"


def test_prepare_preserves_existing_inkstitch_parameters(tmp_path):
    input_path = tmp_path / "input.svg"
    output_path = tmp_path / "prepared.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkstitch="http://inkstitch.org/namespace">'
        '<path d="M0 0 H10 V10 Z" fill="black" inkstitch:row_spacing_mm="0.25"/>'
        "</svg>",
        encoding="utf-8",
    )

    SvgEmbroideryPreparer().prepare(input_path=input_path, output_path=output_path)

    root = ElementTree.parse(output_path).getroot()
    path = next(root.iter("{http://www.w3.org/2000/svg}path"))
    assert path.attrib[f"{INK}row_spacing_mm"] == "0.25"


def test_prepare_handles_inline_style(tmp_path):
    input_path = tmp_path / "input.svg"
    output_path = tmp_path / "prepared.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 H10" style="fill:none;stroke:#111"/>'
        "</svg>",
        encoding="utf-8",
    )

    result = SvgEmbroideryPreparer().prepare(
        input_path=input_path,
        output_path=output_path,
    )

    assert result.fill_paths == 0
    assert result.stroke_paths == 1


def test_prepare_does_not_fill_open_stroke_path_without_fill_attribute(tmp_path):
    input_path = tmp_path / "input.svg"
    output_path = tmp_path / "prepared.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 H10" stroke="#111"/>'
        "</svg>",
        encoding="utf-8",
    )

    result = SvgEmbroideryPreparer().prepare(
        input_path=input_path,
        output_path=output_path,
    )

    assert result.fill_paths == 0
    assert result.stroke_paths == 1
