from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Approval, Asset, MaintenanceRecord, WorkOrder
from app.models.enums import (
    ApprovalDecision,
    AssetStatus,
    AssetType,
    Criticality,
    MaintenanceType,
    WorkOrderPriority,
    WorkOrderStatus,
)


def seed_reference_data(
    database_session: Session,
    reference_time: datetime,
) -> dict[str, Asset]:
    p101 = Asset(
        asset_code="P-101",
        name="Main Cooling Water Pump",
        asset_type=AssetType.PUMP,
        status=AssetStatus.OPERATIONAL,
        criticality=Criticality.CRITICAL,
        location="Cooling Water Area",
        manufacturer="Flowserve",
        model_number="CW-200",
        description="Primary centrifugal pump for the cooling-water circuit.",
    )
    p102 = Asset(
        asset_code="P-102",
        name="Standby Cooling Water Pump",
        asset_type=AssetType.PUMP,
        status=AssetStatus.STANDBY,
        criticality=Criticality.HIGH,
        location="Cooling Water Area",
        manufacturer="Flowserve",
        model_number="CW-200",
        description="Standby centrifugal pump for the cooling-water circuit.",
    )
    p201 = Asset(
        asset_code="P-201",
        name="Process Transfer Pump",
        asset_type=AssetType.PUMP,
        status=AssetStatus.OPERATIONAL,
        criticality=Criticality.HIGH,
        location="Process Transfer Area",
        manufacturer="KSB",
        model_number="PT-150",
        description="Centrifugal pump used for process-fluid transfer.",
    )
    m101 = Asset(
        asset_code="M-101",
        name="P-101 Induction Motor",
        asset_type=AssetType.MOTOR,
        status=AssetStatus.OPERATIONAL,
        criticality=Criticality.CRITICAL,
        location="Cooling Water Area",
        manufacturer="WEG",
        model_number="M3BP",
        description="Induction motor driving P-101.",
        parent=p101,
    )

    assets = {
        asset.asset_code: asset
        for asset in (
            p101,
            p102,
            p201,
            m101,
        )
    }

    database_session.add_all(assets.values())
    database_session.flush()

    maintenance_records = [
        MaintenanceRecord(
            asset=p101,
            performed_at=reference_time - timedelta(days=120),
            maintenance_type=MaintenanceType.CORRECTIVE,
            summary="Pump and motor alignment correction",
            findings="Elevated axial vibration caused by coupling misalignment.",
            action_taken="Performed laser alignment and verified coupling condition.",
            technician="A. Rahman",
            downtime_hours=4.5,
        ),
        MaintenanceRecord(
            asset=p101,
            performed_at=reference_time - timedelta(days=45),
            maintenance_type=MaintenanceType.PREVENTIVE,
            summary="Bearing lubrication service",
            findings="Grease appeared dark with minor metallic contamination.",
            action_taken="Cleaned grease ports and replenished approved lubricant.",
            technician="S. Kumar",
            downtime_hours=1.5,
        ),
        MaintenanceRecord(
            asset=p101,
            performed_at=reference_time - timedelta(days=10),
            maintenance_type=MaintenanceType.INSPECTION,
            summary="Routine vibration inspection",
            findings="Vibration increased from 3.1 to 3.8 mm/s RMS.",
            action_taken="Recommended closer monitoring of bearings and coupling.",
            technician="N. Farah",
            downtime_hours=0.0,
        ),
        MaintenanceRecord(
            asset=p102,
            performed_at=reference_time - timedelta(days=20),
            maintenance_type=MaintenanceType.PREVENTIVE,
            summary="Standby pump readiness inspection",
            findings="No leakage, abnormal noise, or bearing degradation detected.",
            action_taken="Completed manual rotation and short functional test.",
            technician="A. Rahman",
            downtime_hours=0.5,
        ),
        MaintenanceRecord(
            asset=p201,
            performed_at=reference_time - timedelta(days=60),
            maintenance_type=MaintenanceType.CORRECTIVE,
            summary="Mechanical seal replacement",
            findings="Minor process leakage from worn mechanical seal faces.",
            action_taken="Replaced mechanical seal and completed pressure test.",
            technician="S. Kumar",
            downtime_hours=6.0,
        ),
        MaintenanceRecord(
            asset=m101,
            performed_at=reference_time - timedelta(days=90),
            maintenance_type=MaintenanceType.PREVENTIVE,
            summary="Motor electrical and bearing inspection",
            findings="Insulation resistance acceptable; bearings serviceable.",
            action_taken="Cleaned terminal box and lubricated motor bearings.",
            technician="L. Chong",
            downtime_hours=2.0,
        ),
        MaintenanceRecord(
            asset=m101,
            performed_at=reference_time - timedelta(days=12),
            maintenance_type=MaintenanceType.PREDICTIVE,
            summary="Motor current and vibration review",
            findings="Small upward trend in current and drive-end vibration.",
            action_taken="Recommended correlation with P-101 pump vibration.",
            technician="N. Farah",
            downtime_hours=0.0,
        ),
    ]

    historical_work_order = WorkOrder(
        work_order_number="WO-HIST-0001",
        asset=p201,
        title="Replace leaking P-201 mechanical seal",
        description="Replace the worn mechanical seal and verify pressure integrity.",
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.EXECUTED,
        proposed_by="maintenance-planner",
        idempotency_key="seed-p201-seal-replacement-v1",
        executed_at=reference_time - timedelta(days=59, hours=20),
        execution_summary="Mechanical seal replaced and pressure test passed.",
    )
    historical_approval = Approval(
        work_order=historical_work_order,
        request_version=1,
        decision=ApprovalDecision.APPROVED,
        requested_by="maintenance-planner",
        decided_by="maintenance-supervisor",
        decided_at=reference_time - timedelta(days=60, hours=-2),
        decision_reason="Leakage required planned corrective maintenance.",
        consumed_at=reference_time - timedelta(days=59, hours=20),
    )

    pending_work_order = WorkOrder(
        work_order_number="WO-PROP-0001",
        asset=p101,
        title="Inspect elevated P-101 vibration",
        description=(
            "Inspect pump bearings, coupling alignment, lubrication condition, "
            "and motor drive-end vibration."
        ),
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        proposed_by="seed-maintenance-agent",
        idempotency_key="seed-p101-vibration-investigation-v1",
    )
    pending_approval = Approval(
        work_order=pending_work_order,
        request_version=1,
        decision=ApprovalDecision.PENDING,
        requested_by="seed-maintenance-agent",
        decision_reason="Awaiting human maintenance-supervisor decision.",
    )

    database_session.add_all(
        [
            *maintenance_records,
            historical_approval,
            pending_approval,
        ]
    )

    return assets
