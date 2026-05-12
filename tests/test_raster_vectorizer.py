from app.backend.adapters.raster_vectorizer import RasterVectorizer


def test_build_imagemagick_command(tmp_path):
    vectorizer = RasterVectorizer(
        imagemagick_path="convert",
        potrace_path="potrace",
        timeout_seconds=1,
        max_dimension=512,
    )

    command = vectorizer._build_imagemagick_command(
        tmp_path / "input.png",
        tmp_path / "output.pbm",
    )

    assert command == [
        "convert",
        str(tmp_path / "input.png"),
        "-auto-orient",
        "-resize",
        "512x512>",
        "-strip",
        "-alpha",
        "remove",
        "-background",
        "white",
        "-colorspace",
        "Gray",
        "-despeckle",
        "-threshold",
        "60%",
        "-monochrome",
        str(tmp_path / "output.pbm"),
    ]


def test_build_potrace_command(tmp_path):
    vectorizer = RasterVectorizer(
        imagemagick_path="convert",
        potrace_path="potrace",
        timeout_seconds=1,
    )

    command = vectorizer._build_potrace_command(
        tmp_path / "input.pbm",
        tmp_path / "output.svg",
    )

    assert command == [
        "potrace",
        str(tmp_path / "input.pbm"),
        "--svg",
        "--output",
        str(tmp_path / "output.svg"),
    ]
