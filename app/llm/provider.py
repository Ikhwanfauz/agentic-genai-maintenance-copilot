from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
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


def _build_azure_v1_base_url(endpoint: str) -> str:
    normalized_endpoint = endpoint.rstrip("/")

    if normalized_endpoint.endswith("/openai/v1"):
        return f"{normalized_endpoint}/"

    return f"{normalized_endpoint}/openai/v1/"


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
            reasoning_effort=resolved_settings.llm_reasoning_effort,
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

    return ChatOpenAI(
        model=deployment,
        base_url=_build_azure_v1_base_url(endpoint),
        api_key=api_key,
        reasoning_effort=resolved_settings.llm_reasoning_effort,
        timeout=resolved_settings.llm_timeout_seconds,
        max_retries=resolved_settings.llm_max_retries,
    )
