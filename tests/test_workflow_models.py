from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.models import Approval, Asset, WorkOrder
from app.models.enums import (
    ApprovalDecision,
    AssetStatus,
    AssetType,
    Criticality,
    WorkOrderPriority,
    WorkOrderStatus,
)


def test_work_order_and_pending_approval_can_be_persisted() -> None:
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        Base.metadata.create_all(test_engine)

        with Session(test_engine) as database_session:
            asset = Asset(
                asset_code="P-101",
                name="Main Cooling Water Pump",
                asset_type=AssetType.PUMP,
                status=AssetStatus.OPERATIONAL,
                criticality=Criticality.CRITICAL,
                location="Cooling Water Area",
            )
            work_order = WorkOrder(
                work_order_number="WO-TEST-0001",
                asset=asset,
                title="Inspect elevated pump vibration",
                description="Inspect bearings, coupling, alignment, and lubrication condition.",
                priority=WorkOrderPriority.HIGH,
                proposed_by="maintenance-agent",
                idempotency_key="test-investigation-P101-v1",
            )
            approval = Approval(
                work_order=work_order,
                request_version=1,
                requested_by="maintenance-agent",
            )

            database_session.add(approval)
            database_session.commit()
            database_session.refresh(work_order)
            database_session.refresh(approval)

            assert work_order.status is WorkOrderStatus.PROPOSED
            assert work_order.revision == 1
            assert approval.decision is ApprovalDecision.PENDING
            assert approval.approval_scope == "execute_work_order"
            assert approval.work_order_id == work_order.id
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
