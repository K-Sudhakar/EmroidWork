from app.backend.adapters.inkstitch_adapter import InkstitchExecutionError
from app.backend.workers.job_worker import _format_conversion_error


def test_format_conversion_error_includes_stderr_summary():
    error = InkstitchExecutionError(
        "Ink/Stitch conversion failed.",
        stderr="first line\nsecond line",
        exit_code=1,
    )

    assert (
        _format_conversion_error(error)
        == "Ink/Stitch conversion failed. Detail: first line second line"
    )


def test_format_conversion_error_uses_message_without_stderr():
    error = InkstitchExecutionError("Ink/Stitch conversion failed.", stderr="")

    assert _format_conversion_error(error) == "Ink/Stitch conversion failed."
