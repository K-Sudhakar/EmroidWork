import subprocess
import zipfile

import app.backend.adapters.inkstitch_adapter as inkstitch_adapter_module
from app.backend.adapters.inkstitch_adapter import InkstitchAdapter, InkstitchExecutionError
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
        "--format-threadlist=True",
        str(tmp_path / "input.svg"),
    ]


def test_build_export_execution_command_wraps_with_xvfb_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(inkstitch_adapter_module.shutil, "which", lambda name: name)
    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=tmp_path / "inkstitch",
        timeout_seconds=1,
        use_xvfb=True,
    )

    command = adapter._build_export_execution_command(
        tmp_path / "inkstitch",
        tmp_path / "input.svg",
    )

    assert command == [
        "xvfb-run",
        "--auto-servernum",
        "--server-args=-screen 0 1024x768x24",
        str(tmp_path / "inkstitch"),
        "--extension=zip",
        "--format-dst=True",
        "--format-threadlist=True",
        str(tmp_path / "input.svg"),
    ]


def test_build_export_execution_command_uses_direct_command_by_default(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(inkstitch_adapter_module.shutil, "which", lambda name: name)
    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=tmp_path / "inkstitch",
        timeout_seconds=1,
    )

    command = adapter._build_export_execution_command(
        tmp_path / "inkstitch",
        tmp_path / "input.svg",
    )

    assert command == [
        str(tmp_path / "inkstitch"),
        "--extension=zip",
        "--format-dst=True",
        "--format-threadlist=True",
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


def test_extract_optional_thread_list_from_zip(tmp_path):
    zip_path = tmp_path / "result.zip"
    output_path = tmp_path / "output.threadlist.txt"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("design.txt", b"thread-list")

    extracted = InkstitchAdapter._extract_optional_extension_from_zip(
        zip_path=zip_path,
        output_path=output_path,
        extensions=(".txt",),
    )

    assert extracted is True
    assert output_path.read_bytes() == b"thread-list"


def test_extract_dst_from_invalid_zip_includes_output_preview(tmp_path):
    zip_path = tmp_path / "result.zip"
    output_path = tmp_path / "output.dst"
    zip_path.write_text("Ink/Stitch warning: no stitchable elements found\n", encoding="utf-8")

    try:
        InkstitchAdapter._extract_format_from_zip(
            zip_path=zip_path,
            output_path=output_path,
            output_format=OutputFormat.DST,
        )
    except InkstitchExecutionError as exc:
        assert exc.message == "Ink/Stitch did not return a valid zip export archive."
        assert exc.stdout == "Ink/Stitch warning: no stitchable elements found"
    else:
        raise AssertionError("Expected InkstitchExecutionError")


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


def test_resolve_inkstitch_binary_from_extracted_extension_directory(tmp_path):
    extension_root = tmp_path / "extensions"
    binary = extension_root / "inkstitch" / "bin" / "inkstitch"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=extension_root,
        inkstitch_bin_path=None,
        timeout_seconds=1,
    )

    assert adapter._resolve_inkstitch_binary() == binary


def test_convert_timeout_includes_configured_limit_and_cleans_temp_zip(
    tmp_path,
    monkeypatch,
):
    binary = tmp_path / "inkstitch"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    temp_zip_path = tmp_path / "output.zip"

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="inkstitch", timeout=300, stderr=b"busy")

    monkeypatch.setattr(inkstitch_adapter_module.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(inkstitch_adapter_module.subprocess, "run", timeout_run)

    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=binary,
        timeout_seconds=300,
    )

    try:
        adapter.convert(
            input_path=tmp_path / "input.svg",
            output_path=tmp_path / "output.dst",
            output_format=OutputFormat.DST,
            temp_zip_path=temp_zip_path,
        )
    except InkstitchExecutionError as exc:
        assert exc.message == "Ink/Stitch conversion timed out after 300 seconds."
        assert exc.stderr == "busy"
        assert exc.timed_out is True
        assert not temp_zip_path.exists()
    else:
        raise AssertionError("Expected InkstitchExecutionError")


def test_convert_retries_with_xvfb_after_x_display_error(tmp_path, monkeypatch):
    binary = tmp_path / "inkstitch"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    input_path = tmp_path / "input.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>',
        encoding="utf-8",
    )
    temp_zip_path = tmp_path / "output.zip"
    commands = []

    def fake_run_export_command(_self, command, zip_path, _timeout_seconds):
        commands.append(command)
        if len(commands) == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                stderr=b"Unable to access the X Display, is $DISPLAY set properly?",
            )
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("design.dst", b"dst-bytes")
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(inkstitch_adapter_module.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(inkstitch_adapter_module.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        InkstitchAdapter,
        "_run_export_command",
        fake_run_export_command,
    )

    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=binary,
        timeout_seconds=300,
        use_xvfb=False,
    )

    result = adapter.convert(
        input_path=input_path,
        output_path=tmp_path / "output.dst",
        output_format=OutputFormat.DST,
        temp_zip_path=temp_zip_path,
    )

    assert result.output_path.read_bytes() == b"dst-bytes"
    assert commands[0][0] == str(binary)
    assert commands[1][:3] == [
        "xvfb-run",
        "--auto-servernum",
        "--server-args=-screen 0 1024x768x24",
    ]


def test_estimate_timeout_uses_base_for_simple_svg(tmp_path):
    input_path = tmp_path / "input.svg"
    input_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>',
        encoding="utf-8",
    )
    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=tmp_path / "inkstitch",
        timeout_seconds=300,
        max_timeout_seconds=900,
    )

    assert adapter._estimate_timeout_seconds(input_path) == 300


def test_estimate_timeout_scales_with_svg_complexity_and_respects_cap(tmp_path):
    input_path = tmp_path / "input.svg"
    paths = "".join('<path d="{}"/>'.format("M0 0 " * 2000) for _ in range(300))
    input_path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg">{paths}</svg>',
        encoding="utf-8",
    )
    adapter = InkstitchAdapter(
        inkscape_path="python",
        extension_path=tmp_path,
        inkstitch_bin_path=tmp_path / "inkstitch",
        timeout_seconds=300,
        max_timeout_seconds=420,
    )

    assert adapter._estimate_timeout_seconds(input_path) == 420
