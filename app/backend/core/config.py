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
    inkstitch_timeout_seconds: int = Field(default=120, ge=1)
    imagemagick_path: str = "convert"
    potrace_path: str = "potrace"
    raster_vectorize_timeout_seconds: int = Field(default=120, ge=1)

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
