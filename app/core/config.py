from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic GenAI Maintenance Copilot"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite:///./data/maintenance_copilot.db"

    engineering_docs_path: str = "./data/engineering_docs"
    vector_store_path: str = "./data/chroma"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    engineering_docs_collection: str = "engineering_docs"


model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)


@lru_cache
def get_settings() -> Settings:
    return Settings()
