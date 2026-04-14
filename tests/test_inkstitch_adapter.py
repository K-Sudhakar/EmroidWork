import zipfile

from app.backend.adapters.inkstitch_adapter import InkstitchAdapter
from app.backend.models.job import OutputFormat


def test_build_zip_export_command(tmp_path):
    command = InkstitchAdapter._build_zip_export_command(
        tmp_path / "inkstitch",
        tmp_path / "input.svg",
    )
    assert command == [
        str(tmp_path / "inkstitch"),
        "--extension=zip",
        "--format-dst=True",
        str(tmp_path / "input.svg"),
    ]


def test_extract_dst_from_zip(tmp_path):
    zip_path = tmp_path / "result.zip"
    output_path = tmp_path / "output.dst"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("design.dst", b"dst-bytes")

    InkstitchAdapter._extract_format_from_zip(
        zip_path=zip_path,
        output_path=output_path,
        output_format=OutputFormat.DST,
    )

    assert output_path.read_bytes() == b"dst-bytes"
