from dataclasses import dataclass
from pathlib import Path


_DST_HEADER_BYTES = 512
_DST_RECORD_BYTES = 3
_DST_END_RECORD = b"\x00\x00\xf3"


@dataclass(frozen=True)
class DstValidationReport:
    stitch_count: int
    jump_count: int
    color_change_count: int
    width_mm: float
    height_mm: float


class DstValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DstValidator:
    def __init__(
        self,
        *,
        min_stitches: int = 1,
        max_stitches: int = 100000,
        max_width_mm: float = 100,
        max_height_mm: float = 100,
    ) -> None:
        self.min_stitches = min_stitches
        self.max_stitches = max_stitches
        self.max_width_mm = max_width_mm
        self.max_height_mm = max_height_mm

    def validate(self, path: Path) -> DstValidationReport:
        report = self.inspect(path)
        if report.stitch_count < self.min_stitches:
            raise DstValidationError(
                f"DST output contains {report.stitch_count} stitches; "
                f"minimum is {self.min_stitches}."
            )
        if report.stitch_count > self.max_stitches:
            raise DstValidationError(
                f"DST output contains {report.stitch_count} stitches; "
                f"maximum is {self.max_stitches}."
            )
        if report.width_mm > self.max_width_mm:
            raise DstValidationError(
                f"DST width {report.width_mm:g} mm exceeds the configured hoop width "
                f"limit of {self.max_width_mm:g} mm."
            )
        if report.height_mm > self.max_height_mm:
            raise DstValidationError(
                f"DST height {report.height_mm:g} mm exceeds the configured hoop height "
                f"limit of {self.max_height_mm:g} mm."
            )
        return report

    def inspect(self, path: Path) -> DstValidationReport:
        data = path.read_bytes()
        if len(data) < _DST_HEADER_BYTES + _DST_RECORD_BYTES:
            raise DstValidationError("DST output is too small to contain stitch data.")
        body = data[_DST_HEADER_BYTES:]
        if len(body) % _DST_RECORD_BYTES != 0:
            raise DstValidationError("DST output has an invalid record length.")

        x = 0
        y = 0
        min_x = max_x = x
        min_y = max_y = y
        stitch_count = 0
        jump_count = 0
        color_change_count = 0
        end_seen = False

        for index in range(0, len(body), _DST_RECORD_BYTES):
            record = body[index : index + _DST_RECORD_BYTES]
            if record == _DST_END_RECORD:
                end_seen = True
                break

            dx, dy = _decode_delta(record)
            x += dx
            y += dy
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            command = _decode_command(record)
            if command == "color_change":
                color_change_count += 1
            elif command == "jump":
                jump_count += 1
            else:
                stitch_count += 1

        if not end_seen:
            raise DstValidationError("DST output is missing the end record.")

        return DstValidationReport(
            stitch_count=stitch_count,
            jump_count=jump_count,
            color_change_count=color_change_count,
            width_mm=_dst_units_to_mm(max_x - min_x),
            height_mm=_dst_units_to_mm(max_y - min_y),
        )


def _decode_delta(record: bytes) -> tuple[int, int]:
    b0, b1, b2 = record
    x = 0
    y = 0
    if b0 & 0x01:
        x += 9
    if b0 & 0x02:
        x -= 9
    if b0 & 0x04:
        y -= 9
    if b0 & 0x08:
        y += 9
    if b0 & 0x10:
        x += 1
    if b0 & 0x20:
        x -= 1
    if b0 & 0x40:
        y -= 1
    if b0 & 0x80:
        y += 1
    if b1 & 0x01:
        x += 27
    if b1 & 0x02:
        x -= 27
    if b1 & 0x04:
        y -= 27
    if b1 & 0x08:
        y += 27
    if b1 & 0x10:
        x += 3
    if b1 & 0x20:
        x -= 3
    if b1 & 0x40:
        y -= 3
    if b1 & 0x80:
        y += 3
    if b2 & 0x10:
        x += 81
    if b2 & 0x20:
        x -= 81
    if b2 & 0x40:
        y -= 81
    if b2 & 0x80:
        y += 81
    return x, y


def _decode_command(record: bytes) -> str:
    b2 = record[2]
    if b2 & 0xC3 == 0xC3:
        return "color_change"
    if b2 & 0x83 == 0x83:
        return "jump"
    return "stitch"


def _dst_units_to_mm(value: int) -> float:
    return value / 10
