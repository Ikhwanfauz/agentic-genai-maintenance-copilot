from pathlib import Path

DOCKERFILE_PATH = Path("Dockerfile")
DOCKERIGNORE_PATH = Path(".dockerignore")


def test_dockerfile_uses_pinned_cpu_runtime() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "FROM python:3.11-slim-bookworm" in content
    assert "ARG TORCH_VERSION=2.11.0" in content
    assert "--index-url https://download.pytorch.org/whl/cpu" in content
    assert '"torch==${TORCH_VERSION}"' in content
    assert "nvidia_" not in content.lower()


def test_dockerfile_enforces_non_root_health_contract() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    user_position = content.index("USER maintenance")
    command_position = content.index('CMD ["python", "-m", "uvicorn"')

    assert user_position < command_position
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "http://127.0.0.1:8000/health" in content
    assert '"--host", "0.0.0.0"' in content


def test_dockerfile_uses_persistent_runtime_paths() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")

    required_runtime_settings = {
        ("DATABASE_URL=sqlite:////app/runtime/maintenance_copilot.db"),
        ("LANGGRAPH_CHECKPOINT_PATH=/app/runtime/langgraph_checkpoints.sqlite"),
        "VECTOR_STORE_PATH=/app/runtime/chroma",
        "HF_HOME=/app/runtime/huggingface",
    }

    for setting in required_runtime_settings:
        assert setting in content


def test_dockerignore_excludes_secrets_and_generated_data() -> None:
    patterns = {
        line.strip()
        for line in DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    required_patterns = {
        ".env",
        ".env.*",
        "data/*.db",
        "data/*.sqlite",
        "data/*.sqlite3",
        "data/chroma/",
        "reports/",
        "tests/",
    }

    assert required_patterns <= patterns
    assert "!.env.example" in patterns
