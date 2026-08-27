from pathlib import Path

COMPOSE_PATH = Path("compose.yaml")


def load_compose_content() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def split_service_content() -> tuple[str, str]:
    content = load_compose_content()
    api_content, dashboard_content = content.split(
        "  dashboard:",
        maxsplit=1,
    )

    return api_content, dashboard_content


def test_compose_declares_api_dashboard_and_volume() -> None:
    content = load_compose_content()

    assert "  api:" in content
    assert "  dashboard:" in content
    assert "  maintenance-runtime:" in content
    assert "maintenance-runtime:/app/runtime" in content


def test_compose_initializes_only_api_service() -> None:
    api_content, dashboard_content = split_service_content()

    assert 'INITIALIZE_APPLICATION_DATA: "true"' in api_content
    assert 'INITIALIZE_APPLICATION_DATA: "false"' in dashboard_content
    assert "env_file:" in api_content
    assert "env_file:" not in dashboard_content


def test_dashboard_uses_internal_healthy_api() -> None:
    _, dashboard_content = split_service_content()

    assert "MAINTENANCE_API_BASE_URL: http://api:8000" in dashboard_content
    assert "condition: service_healthy" in (dashboard_content)
    assert "http://127.0.0.1:8501/_stcore/health" in dashboard_content


def test_compose_applies_container_security_boundary() -> None:
    content = load_compose_content()

    assert content.count("no-new-privileges:true") == 2
    assert content.count("cap_drop:") == 2
    assert content.count("restart: unless-stopped") == 2
