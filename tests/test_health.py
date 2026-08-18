from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_expected_response() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "Agentic GenAI Maintenance Copilot",
        "version": "0.1.0",
    }
