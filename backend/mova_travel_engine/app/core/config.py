"""Application settings, loaded from environment variables / .env.

Secrets are SecretStr so they never leak through repr(), logs or JSON dumps.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./mova.db"

    google_maps_api_key: SecretStr | None = None
    weather_api_key: SecretStr | None = None
    llm_provider: str = "none"
    llm_api_key: SecretStr | None = None

    osm_enabled: bool = True
    osm_cache_ttl_seconds: int = 21600
    osm_search_radius_m: int = 20000
    osm_max_places: int = 80
    osm_planner_visit_minutes: int = 90
    osm_planner_intensity: int = 2

    cors_origins: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000"
    allow_synthetic_data: bool = True

    data_dir: Path = PROJECT_ROOT / "data"
    models_dir: Path = PROJECT_ROOT / "models"

    @field_validator(
        "google_maps_api_key", "weather_api_key", "llm_api_key", mode="before"
    )
    @classmethod
    def _blank_secret_is_none(cls, v):
        # "KEY=" in .env yields "" - treat as "not configured".
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_google_maps(self) -> bool:
        return self.google_maps_api_key is not None

    @property
    def has_weather_key(self) -> bool:
        return self.weather_api_key is not None

    @property
    def has_llm(self) -> bool:
        return self.llm_provider != "none" and self.llm_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
