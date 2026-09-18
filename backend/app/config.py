from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
    env_file=("../.env", ".env"),
        env_prefix="EXPENSE_V2_",
        extra="ignore",
    )

    database_url: str = "sqlite+pysqlite:///data/expense-v2.db"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 720
    object_storage_path: Path = Path("data/objects")
    primary_currency: str = "INR"
    supported_currencies: list[str] = Field(default_factory=lambda: ["INR"])
    max_file_size_mb: int = 15
    max_batch_files: int = 10
    max_total_minor_units: int = 100_000_000
    max_agent_steps: int = 16
    max_tool_retries: int = 2
    planner: str = "auto"
    model: str = "qwen/qwen3.8-27b"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    retain_ocr_text: bool = False
    bootstrap_email: str | None = None
    bootstrap_password: str | None = None
    bootstrap_organization: str = "Local Org"
    stale_job_seconds: int = 300
    max_job_attempts: int = 3
    worker_poll_seconds: float = 1.0
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
