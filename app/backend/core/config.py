from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Embroidery Processing API"
    environment: str = "local"
    log_level: str = "INFO"

    data_path: Path = Path("/data")
    max_file_size: int = Field(default=10 * 1024 * 1024, ge=1)
    allowed_origins: str = "*"

    inkscape_path: str = "inkscape"
    inkstitch_ext_path: Path | None = Path("/root/.config/inkscape/extensions")
    inkstitch_bin_path: Path | None = None
    inkstitch_timeout_seconds: int = Field(default=300, ge=1)
    inkstitch_max_timeout_seconds: int = Field(default=900, ge=1)
    imagemagick_path: str = "convert"
    potrace_path: str = "potrace"
    raster_vectorize_timeout_seconds: int = Field(default=120, ge=1)
    raster_max_dimension: int = Field(default=512, ge=64)
    raster_vectorize_mode: str = "color"
    raster_vectorize_threshold: int = Field(default=160, ge=0, le=255)
    raster_vectorize_colors: int = Field(default=8, ge=1, le=24)
    raster_background_tolerance: int = Field(default=0, ge=0)
    raster_preserve_background: bool = False
    raster_turdsize: int = Field(default=8, ge=0)
    raster_opttolerance: float = Field(default=0.2, ge=0)
    raster_max_path_data_chars: int = Field(default=250000, ge=1)
    raster_min_dimension: int = Field(default=192, ge=64)
    raster_min_colors: int = Field(default=2, ge=1, le=24)
    svg_preflight_max_elements: int = Field(default=5000, ge=1)
    svg_preflight_max_paths: int = Field(default=2000, ge=1)
    svg_preflight_max_path_data_chars: int = Field(default=250000, ge=1)
    svg_preflight_max_dimension: int = Field(default=10000, ge=1)
    svg_preflight_allow_embedded_images: bool = False
    svg_normalize_with_inkscape: bool = True
    design_max_width_mm: float = Field(default=100, gt=0)
    design_max_height_mm: float = Field(default=100, gt=0)
    design_min_width_mm: float = Field(default=1, gt=0)
    design_min_height_mm: float = Field(default=1, gt=0)
    design_min_path_dimension_mm: float = Field(default=0.4, gt=0)
    design_max_tiny_paths: int = Field(default=20, ge=0)
    dst_min_stitches: int = Field(default=1, ge=0)
    dst_max_stitches: int = Field(default=100000, ge=1)
    embroidery_fill_row_spacing_mm: float = Field(default=0.4, gt=0)
    embroidery_fill_max_stitch_length_mm: float = Field(default=4.0, gt=0)
    embroidery_fill_underlay: bool = True
    embroidery_fill_underlay_inset_mm: float = Field(default=0.4, ge=0)
    embroidery_fill_underlay_row_spacing_mm: float = Field(default=3.0, gt=0)
    embroidery_running_stitch_length_mm: float = Field(default=2.5, gt=0)
    embroidery_running_stitch_repeats: int = Field(default=1, ge=1)
    embroidery_lock_stitches: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def input_dir(self) -> Path:
        return self.data_path / "input"

    @property
    def output_dir(self) -> Path:
        return self.data_path / "output"

    @property
    def temp_dir(self) -> Path:
        return self.data_path / "temp"

    @property
    def jobs_dir(self) -> Path:
        return self.data_path / "jobs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
