from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, loaded from environment variables.

    Nothing here is exposed to the browser: the frontend only ever talks to
    the backend API, never directly to OpenRouter or the database.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "MedTech Reimbursement Readiness Agent"
    app_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_port: int = 3000
    # Comma-separated extra CORS origins, e.g. the deployed Vercel URL
    # (https://your-app.vercel.app) -- the localhost origins below always
    # stay allowed regardless, so local dev keeps working unchanged.
    additional_cors_origins: str = ""

    database_url: str = "postgresql+psycopg://medtech:change-me@postgres:5432/medtech_agent"
    redis_url: str = "redis://redis:6379/0"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""
    openrouter_extraction_model: str = ""
    openrouter_synthesis_model: str = ""
    openrouter_citation_model: str = ""
    openrouter_zdr: bool = True
    openrouter_require_parameters: bool = True
    openrouter_http_referer: str = "http://localhost:3000"
    openrouter_app_title: str = "MedTech Reimbursement Readiness Agent"

    openfda_base_url: str = "https://api.fda.gov"
    cms_coverage_base_url: str = "https://api.coverage.cms.gov"

    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16

    storage_root: str = "/app/data/storage"
    max_upload_mb: int = 100
    max_crawl_pages: int = 250
    max_crawl_depth: int = 4
    crawl_delay_ms: int = 750
    allow_ocr: bool = False
    allow_lan_access: bool = False

    secret_key: str = "replace-with-random-value"
    log_level: str = "INFO"
    store_raw_model_responses: bool = True
    store_prompt_logs: bool = True

    prompts_root: str = "/app/prompts"

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root)

    @property
    def prompts_path(self) -> Path:
        return Path(self.prompts_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
