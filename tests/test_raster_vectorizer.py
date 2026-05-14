from app.backend.adapters.raster_vectorizer import RasterVectorizer
from PIL import Image


def test_build_potrace_command(tmp_path):
    vectorizer = RasterVectorizer(
        potrace_path="potrace",
        timeout_seconds=1,
        turdsize=8,
        opttolerance=0.2,
    )

    command = vectorizer._build_potrace_command(tmp_path / "input.pbm", tmp_path / "output.svg")

    assert command == [
        "potrace",
        str(tmp_path / "input.pbm"),
        "--svg",
        "--flat",
        "--turdsize",
        "8",
        "--opttolerance",
        "0.2",
        "-o",
        str(tmp_path / "output.svg"),
    ]


def test_resize_if_needed_keeps_aspect_ratio(tmp_path):
    vectorizer = RasterVectorizer(
        timeout_seconds=1,
        max_dimension=100,
    )
    path = tmp_path / "input.png"
    Image.new("RGB", (300, 150), "white").save(path)

    img = vectorizer._resize_if_needed(vectorizer._open_image(path))

    assert img.size == (100, 50)
