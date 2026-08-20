from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.llm.exceptions import LLMConfigurationError
from app.llm.provider import create_chat_model


def test_settings_define_safe_llm_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-5.6-luna"
    assert settings.openai_api_key is None


def test_openai_provider_requires_api_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key=None,
    )

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        create_chat_model(settings)


def test_openai_provider_builds_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = Mock()
    constructor = Mock(return_value=model)
    monkeypatch.setattr("app.llm.provider.ChatOpenAI", constructor)

    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_model="gpt-5.6-luna",
        openai_api_key="test-openai-key",
        llm_timeout_seconds=20,
        llm_max_retries=1,
    )

    result = create_chat_model(settings)

    assert result is model
    constructor.assert_called_once_with(
        model="gpt-5.6-luna",
        api_key="test-openai-key",
        timeout=20,
        max_retries=1,
    )


def test_azure_provider_requires_configuration() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
    )

    with pytest.raises(LLMConfigurationError, match="AZURE_OPENAI_API_KEY"):
        create_chat_model(settings)


def test_azure_provider_builds_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = Mock()
    constructor = Mock(return_value=model)
    monkeypatch.setattr("app.llm.provider.AzureChatOpenAI", constructor)

    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
        azure_openai_api_key="test-azure-key",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="maintenance-copilot",
        azure_openai_api_version="2026-01-01",
        llm_timeout_seconds=45,
        llm_max_retries=3,
    )

    result = create_chat_model(settings)

    assert result is model
    constructor.assert_called_once_with(
        azure_endpoint="https://example.openai.azure.com",
        azure_deployment="maintenance-copilot",
        api_version="2026-01-01",
        api_key="test-azure-key",
        timeout=45,
        max_retries=3,
    )
