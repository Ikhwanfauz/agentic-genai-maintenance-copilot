from typing import Protocol

import streamlit as st
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.enums import AgentRunStatus
from app.schemas.agent_api import (
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.ui.api_client import (
    MaintenanceApiClient,
    MaintenanceApiClientError,
)
from app.ui.approval_panel import render_approval_panel
from app.ui.operator_actions import refresh_agent_run
from app.ui.run_views import render_run_details

ACTIVE_RUN_STATE_KEY = "maintenance_active_run"

ASSET_OPTIONS: tuple[str | None, ...] = (
    None,
    "P-101",
    "P-102",
    "P-201",
    "M-101",
)


class InvestigationClient(Protocol):
    def start_investigation(
        self,
        request: AgentInvestigationStartRequest,
    ) -> AgentRunResponse: ...


def start_investigation(
    client: InvestigationClient,
    *,
    user_query: str,
    asset_code: str | None,
    max_iterations: int,
) -> AgentRunResponse:
    """Build a typed request and start an investigation."""

    request = AgentInvestigationStartRequest(
        user_query=user_query,
        asset_code=asset_code,
        max_iterations=max_iterations,
    )

    return client.start_investigation(request)


def get_latest_agent_run(
    *,
    api_base_url: str,
    timeout_seconds: float,
    run_id: str,
) -> AgentRunResponse:
    """Retrieve the latest run through the typed API client."""

    with MaintenanceApiClient(
        api_base_url,
        timeout_seconds=timeout_seconds,
    ) as client:
        return refresh_agent_run(
            client,
            run_id,
        )


def store_active_run(
    response: AgentRunResponse,
) -> None:
    """Store JSON-compatible run state across Streamlit reruns."""

    st.session_state[ACTIVE_RUN_STATE_KEY] = response.model_dump(
        mode="json",
    )


def load_active_run() -> AgentRunResponse | None:
    """Restore and revalidate the active run from session state."""

    payload = st.session_state.get(ACTIVE_RUN_STATE_KEY)

    if payload is None:
        return None

    try:
        return AgentRunResponse.model_validate(payload)
    except ValidationError:
        st.session_state.pop(
            ACTIVE_RUN_STATE_KEY,
            None,
        )
        return None


def format_asset_option(
    asset_code: str | None,
) -> str:
    if asset_code is None:
        return "Let the agent identify the asset"

    return asset_code


def render_run_summary(
    run: AgentRunResponse,
) -> None:
    """Render a compact summary of the latest agent run."""

    st.subheader("Current investigation")

    status_label = run.status.value.replace("_", " ").title()

    run_column, thread_column, status_column = st.columns(3)

    run_column.metric(
        "Run ID",
        run.run_id,
    )
    thread_column.metric(
        "Thread ID",
        run.thread_id,
    )
    status_column.metric(
        "Status",
        status_label,
    )

    if run.status == AgentRunStatus.WAITING_FOR_APPROVAL:
        st.warning(
            "This investigation is waiting for a human work-order decision. "
            "Approval controls will be added in the next V6.5 checkpoint."
        )
    elif run.status == AgentRunStatus.FAILED:
        st.error(run.error_message or "The maintenance investigation failed.")
    elif run.status == AgentRunStatus.ABSTAINED:
        st.warning(
            run.final_response or "The agent abstained because the evidence was insufficient."
        )
    elif run.final_response:
        st.success(run.final_response)


def render_dashboard() -> None:
    """Render the maintenance operator dashboard."""

    settings = get_settings()

    st.set_page_config(
        page_title="Maintenance Copilot",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Agentic GenAI Maintenance Copilot")
    st.caption(
        "Grounded rotating-equipment investigation with explicit "
        "human approval for application-level actions."
    )

    st.info(
        "Safety boundary: this copilot does not control machinery, "
        "modify PLC parameters, bypass interlocks, or record physical "
        "maintenance execution."
    )

    with st.sidebar:
        st.header("API connection")

        api_base_url = st.text_input(
            "Maintenance API URL",
            value=settings.maintenance_api_base_url,
            help="FastAPI base URL used by this Streamlit session.",
        )

        api_timeout_seconds = st.number_input(
            "Request timeout (seconds)",
            min_value=1.0,
            max_value=600.0,
            value=settings.maintenance_api_timeout_seconds,
            step=10.0,
        )

        st.caption("Connection settings apply only to this dashboard session.")

    st.subheader("Start investigation")

    with st.form(
        "maintenance_investigation_form",
        clear_on_submit=False,
    ):
        user_query = st.text_area(
            "Equipment issue",
            placeholder=(
                "Example: Investigate increasing vibration and "
                "temperature on the main cooling-water pump."
            ),
            height=140,
            max_chars=4000,
        )

        asset_code = st.selectbox(
            "Asset",
            options=ASSET_OPTIONS,
            format_func=format_asset_option,
        )

        max_iterations = st.slider(
            "Maximum agent iterations",
            min_value=1,
            max_value=10,
            value=6,
            help="Application-owned bound for the model-tool loop.",
        )

        submitted = st.form_submit_button(
            "Start grounded investigation",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            with st.spinner("Gathering evidence and running the bounded investigation..."):
                with MaintenanceApiClient(
                    api_base_url,
                    timeout_seconds=api_timeout_seconds,
                ) as client:
                    response = start_investigation(
                        client,
                        user_query=user_query,
                        asset_code=asset_code,
                        max_iterations=max_iterations,
                    )
        except ValidationError as error:
            first_error = error.errors()[0]
            st.error(f"Invalid investigation request: {first_error['msg']}")
        except ValueError as error:
            st.error(str(error))
        except MaintenanceApiClientError as error:
            st.error(str(error))
        else:
            store_active_run(response)
            st.success(f"Investigation {response.run_id} started successfully.")

    active_run = load_active_run()

    if active_run is not None:
        st.divider()

        refresh_submitted = st.button(
            "Refresh run status",
            key=f"refresh_run_{active_run.run_id}",
        )

        if refresh_submitted:
            try:
                with st.spinner("Retrieving the latest persisted run state..."):
                    refreshed_run = get_latest_agent_run(
                        api_base_url=api_base_url,
                        timeout_seconds=api_timeout_seconds,
                        run_id=active_run.run_id,
                    )
            except (
                MaintenanceApiClientError,
                ValueError,
            ) as error:
                st.error(str(error))
            else:
                store_active_run(refreshed_run)
                st.toast(
                    "Latest agent run loaded.",
                )
                st.rerun()

        render_run_summary(active_run)
        render_run_details(active_run)

        updated_run = render_approval_panel(
            active_run,
            api_base_url=api_base_url,
            timeout_seconds=api_timeout_seconds,
        )

        if updated_run is not None:
            store_active_run(updated_run)
            st.toast(
                "Human decision recorded and workflow resumed.",
            )
            st.rerun()
