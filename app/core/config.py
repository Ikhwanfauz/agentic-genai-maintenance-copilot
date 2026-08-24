from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic GenAI Maintenance Copilot"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite:///./data/maintenance_copilot.db"
    langgraph_checkpoint_path: str = "./data/langgraph_checkpoints.sqlite"

    engineering_docs_path: str = "./data/engineering_docs"
    vector_store_path: str = "./data/chroma"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    engineering_docs_collection: str = "engineering_docs"

    llm_provider: Literal["openai", "azure_openai"] = "openai"
    llm_model: str = "gpt-5.4-mini"
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "low"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)

    openai_api_key: SecretStr | None = None

    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
