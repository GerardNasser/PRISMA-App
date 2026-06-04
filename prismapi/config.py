"""Runtime configuration for the desktop sidecar.

The OS owns the data directory. We resolve it via platform conventions,
falling back to env override for tests. No DATABASE_URL / REDIS_URL / CORS;
this app does not run a server.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_app_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PrismAPI"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PrismAPI"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "PrismAPI"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_data_dir: Path = Field(
        default_factory=_default_app_data_dir, alias="PRISMAPI_DATA_DIR"
    )

    # External outbound HTTP only — no inbound sockets.
    ncbi_email: str | None = Field(default=None, alias="NCBI_EMAIL")
    ncbi_api_key: str | None = Field(default=None, alias="NCBI_API_KEY")
    openalex_email: str | None = Field(default=None, alias="OPENALEX_EMAIL")

    # Safety knobs (Layer 2/4).
    trash_retention_days: int = Field(default=30, alias="PRISMAPI_TRASH_RETENTION_DAYS")
    snapshot_auto_cap: int = Field(default=10, alias="PRISMAPI_SNAPSHOT_AUTO_CAP")

    # LLM advisory (off by default).
    llm_advisory_enabled: bool = Field(default=False, alias="LLM_ADVISORY_ENABLED")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / "prismapi.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.app_data_dir / "snapshots"

    @property
    def projects_assets_dir(self) -> Path:
        return self.app_data_dir / "projects"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.projects_assets_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
