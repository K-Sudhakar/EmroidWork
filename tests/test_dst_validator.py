import pytest

from app.backend.adapters.dst_validator import DstValidationError, DstValidator


def test_dst_validator_accepts_valid_stitch_file(tmp_path):
    path = tmp_path / "output.dst"
    path.write_bytes(_dst_file([b"\x10\x00\x03", b"\x10\x00\x03"]))

    report = DstValidator(min_stitches=1, max_width_mm=1, max_height_mm=1).validate(path)

    assert report.stitch_count == 2
    assert report.width_mm == 0.2
    assert report.height_mm == 0


def test_dst_validator_rejects_empty_design(tmp_path):
    path = tmp_path / "output.dst"
    path.write_bytes(_dst_file([]))

    with pytest.raises(DstValidationError, match="contains 0 stitches"):
        DstValidator(min_stitches=1).validate(path)


def test_dst_validator_rejects_missing_end_record(tmp_path):
    path = tmp_path / "output.dst"
    path.write_bytes(b" " * 512 + b"\x10\x00\x03")

    with pytest.raises(DstValidationError, match="missing the end record"):
        DstValidator().validate(path)


def test_dst_validator_rejects_too_many_stitches(tmp_path):
    path = tmp_path / "output.dst"
    path.write_bytes(_dst_file([b"\x10\x00\x03", b"\x10\x00\x03"]))

    with pytest.raises(DstValidationError, match="maximum is 1"):
        DstValidator(max_stitches=1).validate(path)


def _dst_file(records: list[bytes]) -> bytes:
    return b" " * 512 + b"".join(records) + b"\x00\x00\xf3"
