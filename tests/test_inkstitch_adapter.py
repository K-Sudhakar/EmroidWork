import zipfile

import app.backend.adapters.inkstitch_adapter as inkstitch_adapter_module
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


def test_dependency_status_rejects_non_executable_inkstitch_binary(tmp_path, monkeypatch):
    binary = tmp_path / "inkstitch"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(inkstitch_adapter_module.os, "access", lambda _path, _mode: False)

    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=binary,
        timeout_seconds=1,
    )

    inkscape_ok, extension_ok, detail = adapter.dependency_status()

    assert inkscape_ok is True
    assert extension_ok is False
    assert detail == "Ink/Stitch extension binary is not executable."
