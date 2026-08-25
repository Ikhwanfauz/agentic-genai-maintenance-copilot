from types import TracebackType
from typing import Self
from urllib.parse import urlparse

import httpx2
from pydantic import ValidationError

from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
    AgentRunResponse,
)


class MaintenanceApiClientError(Exception):
    """Base error raised by the maintenance API client."""


class MaintenanceApiConnectionError(MaintenanceApiClientError):
    """Raised when the FastAPI application cannot be reached."""


class MaintenanceApiResponseError(MaintenanceApiClientError):
    """Raised when FastAPI returns an unsuccessful HTTP response."""

    def __init__(
        self,
        status_code: int,
        detail: str,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Maintenance API returned HTTP {status_code}: {detail}")


class MaintenanceApiContractError(MaintenanceApiClientError):
    """Raised when an API response does not match the expected contract."""


class MaintenanceApiClient:
    """Typed synchronous client for the maintenance copilot REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 120.0,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        parsed_base_url = urlparse(normalized_base_url)

        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ValueError("Maintenance API base URL must be a valid HTTP or HTTPS URL.")

        if timeout_seconds <= 0:
            raise ValueError("Maintenance API timeout must be greater than zero.")

        self._client = httpx2.Client(
            base_url=normalized_base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""

        self._client.close()

    def start_investigation(
        self,
        request: AgentInvestigationStartRequest,
    ) -> AgentRunResponse:
        """Start a new grounded maintenance investigation."""

        return self._request(
            "POST",
            "/agent/investigations",
            json=request.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )

    def get_run(
        self,
        run_id: str,
    ) -> AgentRunResponse:
        """Retrieve the current persisted state of an agent run."""

        normalized_run_id = self._normalize_run_id(run_id)

        return self._request(
            "GET",
            f"/agent/runs/{normalized_run_id}",
        )

    def submit_approval(
        self,
        run_id: str,
        request: AgentApprovalDecisionRequest,
    ) -> AgentRunResponse:
        """Submit a human approval or rejection decision."""

        normalized_run_id = self._normalize_run_id(run_id)

        return self._request(
            "POST",
            f"/agent/runs/{normalized_run_id}/approval",
            json=request.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> AgentRunResponse:
        try:
            response = self._client.request(
                method,
                path,
                json=json,
            )
        except httpx2.RequestError as error:
            raise MaintenanceApiConnectionError(
                "The maintenance API could not be reached."
            ) from error

        if not response.is_success:
            raise MaintenanceApiResponseError(
                status_code=response.status_code,
                detail=self._extract_error_detail(response),
            )

        try:
            response_payload = response.json()
        except ValueError as error:
            raise MaintenanceApiContractError(
                "The maintenance API returned invalid JSON."
            ) from error

        try:
            return AgentRunResponse.model_validate(response_payload)
        except ValidationError as error:
            raise MaintenanceApiContractError(
                "The maintenance API response did not match AgentRunResponse."
            ) from error

    @staticmethod
    def _normalize_run_id(run_id: str) -> str:
        normalized_run_id = run_id.strip()

        if not normalized_run_id:
            raise ValueError("Agent run ID must not be empty.")

        if "/" in normalized_run_id or "\\" in normalized_run_id:
            raise ValueError("Agent run ID must not contain path separators.")

        return normalized_run_id

    @staticmethod
    def _extract_error_detail(
        response: httpx2.Response,
    ) -> str:
        fallback_detail = f"Request failed with HTTP {response.status_code}."

        try:
            response_payload = response.json()
        except ValueError:
            return fallback_detail

        if not isinstance(response_payload, dict):
            return fallback_detail

        detail = response_payload.get("detail")

        if isinstance(detail, str) and detail.strip():
            return detail.strip()

        return fallback_detail
