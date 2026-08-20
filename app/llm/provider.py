from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.llm.exceptions import LLMConfigurationError


def _require_secret(secret: SecretStr | None, environment_variable: str) -> str:
    if secret is None or not secret.get_secret_value().strip():
        raise LLMConfigurationError(
            f"{environment_variable} is required for the selected LLM provider."
        )

    return secret.get_secret_value()


def _require_text(value: str | None, environment_variable: str) -> str:
    if value is None or not value.strip():
        raise LLMConfigurationError(
            f"{environment_variable} is required for the selected LLM provider."
        )

    return value.strip()


def create_chat_model(settings: Settings | None = None) -> BaseChatModel:
    resolved_settings = settings or get_settings()

    if resolved_settings.llm_provider == "openai":
        api_key = _require_secret(
            resolved_settings.openai_api_key,
            "OPENAI_API_KEY",
        )

        return ChatOpenAI(
            model=resolved_settings.llm_model,
            api_key=api_key,
            timeout=resolved_settings.llm_timeout_seconds,
            max_retries=resolved_settings.llm_max_retries,
        )

    api_key = _require_secret(
        resolved_settings.azure_openai_api_key,
        "AZURE_OPENAI_API_KEY",
    )
    endpoint = _require_text(
        resolved_settings.azure_openai_endpoint,
        "AZURE_OPENAI_ENDPOINT",
    )
    deployment = _require_text(
        resolved_settings.azure_openai_deployment,
        "AZURE_OPENAI_DEPLOYMENT",
    )
    api_version = _require_text(
        resolved_settings.azure_openai_api_version,
        "AZURE_OPENAI_API_VERSION",
    )

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        azure_deployment=deployment,
        api_version=api_version,
        api_key=api_key,
        timeout=resolved_settings.llm_timeout_seconds,
        max_retries=resolved_settings.llm_max_retries,
    )
