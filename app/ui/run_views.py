from enum import StrEnum

import streamlit as st

from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.agent_api import AgentRunResponse
from app.schemas.diagnosis import MaintenanceDiagnosis


def format_enum_label(
    value: StrEnum,
) -> str:
    return value.value.replace("_", " ").title()


def render_run_details(
    run: AgentRunResponse,
) -> None:
    """Render all available typed investigation results."""

    if run.diagnosis is not None:
        render_diagnosis(run.diagnosis)

    if run.work_order_proposal is not None:
        render_work_order_proposal(
            run.work_order_proposal,
        )

    if run.approval_decision is not None:
        render_approval_decision(
            run.approval_decision,
        )


def render_diagnosis(
    diagnosis: MaintenanceDiagnosis,
) -> None:
    st.subheader("Grounded diagnosis")

    asset_column, outcome_column, confidence_column = st.columns(3)

    asset_column.metric(
        "Asset",
        diagnosis.asset_code or "Not identified",
    )
    outcome_column.metric(
        "Outcome",
        format_enum_label(diagnosis.outcome),
    )
    confidence_column.metric(
        "Confidence",
        format_enum_label(diagnosis.confidence),
    )

    st.markdown("**Summary**")
    st.write(diagnosis.summary)

    st.markdown("**Confidence rationale**")
    st.write(diagnosis.confidence_rationale)

    if diagnosis.abstention_reason:
        st.warning(f"Abstention reason: {diagnosis.abstention_reason}")

    if diagnosis.likely_causes:
        st.markdown("**Likely causes**")

        for cause in diagnosis.likely_causes:
            st.markdown(f"- {cause}")

    if diagnosis.evidence:
        st.markdown("**Evidence and citations**")

        for index, evidence in enumerate(
            diagnosis.evidence,
            start=1,
        ):
            source_label = format_enum_label(
                evidence.source_type,
            )

            with st.expander(f"{index}. {source_label}: {evidence.source_id}"):
                st.write(evidence.summary)
                st.code(
                    evidence.citation,
                    language=None,
                )

    if diagnosis.recommended_actions:
        st.markdown("**Recommended actions**")

        for index, action in enumerate(
            diagnosis.recommended_actions,
            start=1,
        ):
            st.markdown(f"**{index}. {action.action}**")
            st.write(action.rationale)
            st.caption(
                f"Priority: {format_enum_label(action.priority)} · "
                f"State changing: {'Yes' if action.state_changing else 'No'} · "
                "Human approval required: "
                f"{'Yes' if action.requires_human_approval else 'No'}"
            )

    st.markdown("**Safety notes**")

    for safety_note in diagnosis.safety_notes:
        st.markdown(f"- {safety_note}")


def render_work_order_proposal(
    proposal: WorkOrderProposalOutput,
) -> None:
    st.subheader("Proposed work order")

    number_column, priority_column, status_column = st.columns(3)

    number_column.metric(
        "Work order",
        proposal.work_order_number,
    )
    priority_column.metric(
        "Priority",
        format_enum_label(proposal.priority),
    )
    status_column.metric(
        "Status",
        format_enum_label(proposal.status),
    )

    st.markdown(f"**{proposal.title}**")
    st.write(proposal.description)

    st.caption(
        f"Asset: {proposal.asset_code} · "
        f"Work-order ID: {proposal.work_order_id} · "
        f"Approval ID: {proposal.approval_id} · "
        f"Request version: {proposal.request_version}"
    )

    st.caption(
        "Approval scope: application-level work-order approval. "
        "This does not authorize machinery or PLC control."
    )


def render_approval_decision(
    decision: WorkOrderApprovalDecisionOutput,
) -> None:
    st.subheader("Human approval decision")

    decision_column, status_column, operator_column = st.columns(3)

    decision_column.metric(
        "Decision",
        format_enum_label(decision.decision),
    )
    status_column.metric(
        "Work-order status",
        format_enum_label(decision.work_order_status),
    )
    operator_column.metric(
        "Decided by",
        decision.decided_by,
    )

    st.write(decision.decision_reason)
    st.caption(
        f"Decision time: {decision.decided_at.isoformat()} · "
        f"Request version: {decision.request_version}"
    )

    st.info(
        "The decision was recorded at application level only. "
        "No physical maintenance execution was performed or recorded."
    )
