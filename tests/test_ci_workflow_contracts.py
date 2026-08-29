from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/ci.yml")
IMAGE_TAG = "maintenance-copilot:ci"
CONTAINER_NAME = "maintenance-copilot-ci"


def load_workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def load_container_job_text() -> str:
    workflow = load_workflow_text()
    marker = "\n  container:\n"

    assert marker in workflow

    return workflow.split(marker, maxsplit=1)[1]


def test_quality_job_compiles_azure_infrastructure() -> None:
    workflow = load_workflow_text()
    bicep_command = "az bicep build --file infra/foundation.bicep --stdout > /dev/null"

    assert bicep_command in workflow
    assert workflow.index(bicep_command) < workflow.index("python -m pytest")


def test_container_job_waits_for_quality_gate() -> None:
    container_job = load_container_job_text()

    assert "needs: quality" in container_job
    assert "runs-on: ubuntu-latest" in container_job
    assert "timeout-minutes: 25" in container_job


def test_container_job_builds_and_verifies_non_root_image() -> None:
    container_job = load_container_job_text()

    assert f"docker build --tag {IMAGE_TAG} ." in container_job
    assert f"docker image inspect {IMAGE_TAG}" in container_job
    assert ')" = "maintenance"' in container_job


def test_container_job_starts_without_hosted_model_credentials() -> None:
    container_job = load_container_job_text()

    assert f"--name {CONTAINER_NAME}" in container_job
    assert "--publish 127.0.0.1:8000:8000" in container_job
    assert "--env-file" not in container_job
    assert "AZURE_OPENAI_API_KEY" not in container_job


def test_container_job_requires_successful_health_response() -> None:
    container_job = load_container_job_text()

    assert "curl --fail --silent" in container_job
    assert "http://127.0.0.1:8000/health" in container_job
    assert "API did not become healthy within 300 seconds." in container_job


def test_container_job_always_logs_and_removes_container() -> None:
    container_job = load_container_job_text()

    assert container_job.count("if: always()") == 2
    assert f"docker logs {CONTAINER_NAME} || true" in container_job
    assert f"docker rm --force {CONTAINER_NAME} || true" in container_job
