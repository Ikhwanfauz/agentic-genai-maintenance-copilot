import streamlit as st
from pydantic import ValidationError

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.agent_api import AgentRunResponse
from app.ui.api_client import (
    MaintenanceApiClient,
    MaintenanceApiClientError,
    MaintenanceApiResponseError,
)
from app.ui.operator_actions import (
    OperatorActionContextError,
    submit_work_order_decision,
)


def render_approval_panel(
    run: AgentRunResponse,
    *,
    api_base_url: str,
    timeout_seconds: float,
) -> AgentRunResponse | None:
    """Render and apply an explicit human work-order decision."""

    if run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
        return None

    proposal = run.work_order_proposal

    if proposal is None:
        st.error("The waiting run has no valid work-order proposal.")
        return None

    st.subheader("Human decision required")

    st.warning(
        "Review the grounded diagnosis, citations, recommended action, "
        "and proposed work order before making a decision."
    )

    with st.form(
        (f"approval_form_{run.run_id}_{proposal.request_version}"),
        clear_on_submit=False,
    ):
        decided_by = st.text_input(
            "Operator name or identifier",
            max_chars=100,
        )

        decision_reason = st.text_area(
            "Decision reason",
            placeholder=("Explain why this work order should be approved or rejected."),
            height=120,
            max_chars=2000,
        )

        approve_column, reject_column = st.columns(2)

        with approve_column:
            approve_submitted = st.form_submit_button(
                "Approve work order",
                type="primary",
                use_container_width=True,
            )

        with reject_column:
            reject_submitted = st.form_submit_button(
                "Reject work order",
                use_container_width=True,
            )

    if not approve_submitted and not reject_submitted:
        return None

    decision = ApprovalDecision.APPROVED if approve_submitted else ApprovalDecision.REJECTED

    try:
        with st.spinner("Applying the human decision and resuming the workflow..."):
            with MaintenanceApiClient(
                api_base_url,
                timeout_seconds=timeout_seconds,
            ) as client:
                return submit_work_order_decision(
                    client,
                    run,
                    decision=decision,
                    decided_by=decided_by,
                    decision_reason=decision_reason,
                )
    except ValidationError as error:
        first_error = error.errors()[0]
        st.error(f"Invalid human decision: {first_error['msg']}")
    except OperatorActionContextError as error:
        st.error(str(error))
    except MaintenanceApiResponseError as error:
        if error.status_code == 409:
            st.error(
                "The approval state changed or this decision is stale. "
                "Refresh the run before trying again."
            )
        else:
            st.error(str(error))
    except (
        MaintenanceApiClientError,
        ValueError,
    ) as error:
        st.error(str(error))

    return None
