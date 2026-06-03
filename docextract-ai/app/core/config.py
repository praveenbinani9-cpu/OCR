from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Core
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    allowed_hosts: str = Field(default="*")

    # Database
    database_url: str = Field(...)

    # Redis / Celery
    redis_url: str = Field(...)

    # S3 / MinIO
    s3_endpoint: str = Field(...)
    s3_bucket: str = Field(...)
    s3_access_key: str = Field(...)
    s3_secret_key: str = Field(...)
    s3_region: str = Field(default="us-east-1")

    # LLM
    anthropic_api_key: str = Field(default="")
    emergent_llm_key: str = Field(default="")
    llm_provider: str = Field(default="emergent")  # "emergent" | "anthropic"
    llm_model: str = Field(default="claude-4-sonnet-20250514")

    # Auth
    jwt_secret: str = Field(...)
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60)

    # OCR
    ocr_engine: str = Field(default="tesseract")  # "paddle" | "tesseract"

    # Limits
    max_upload_mb: int = Field(default=25)
    rate_limit_default: str = Field(default="60/minute")
    webhook_timeout_seconds: int = Field(default=10)

    # Observability
    sentry_dsn: str = Field(default="")

    @property
    def allowed_hosts_list(self) -> List[str]:
        if self.allowed_hosts == "*":
            return ["*"]
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
