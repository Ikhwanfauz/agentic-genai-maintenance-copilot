from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.session import create_database_engine
from app.models import Approval, Asset, MaintenanceRecord, WorkOrder
from app.models.enums import ApprovalDecision, WorkOrderStatus


def test_reference_data_can_be_seeded() -> None:
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")
    reference_time = datetime(2026, 8, 19, tzinfo=UTC)

    try:
        Base.metadata.create_all(test_engine)

        with Session(test_engine) as database_session:
            seed_reference_data(database_session, reference_time)
            database_session.commit()

            asset_count = database_session.scalar(select(func.count()).select_from(Asset))
            maintenance_count = database_session.scalar(
                select(func.count()).select_from(MaintenanceRecord)
            )
            work_order_count = database_session.scalar(select(func.count()).select_from(WorkOrder))
            approval_count = database_session.scalar(select(func.count()).select_from(Approval))

            motor = database_session.scalar(select(Asset).where(Asset.asset_code == "M-101"))
            pending_work_order = database_session.scalar(
                select(WorkOrder).where(WorkOrder.status == WorkOrderStatus.PENDING_APPROVAL)
            )
            pending_approval = database_session.scalar(
                select(Approval).where(Approval.work_order_id == pending_work_order.id)
            )

            assert asset_count == 4
            assert maintenance_count == 7
            assert work_order_count == 2
            assert approval_count == 2

            assert motor is not None
            assert motor.parent is not None
            assert motor.parent.asset_code == "P-101"

            assert pending_work_order is not None
            assert pending_approval is not None
            assert pending_approval.decision is ApprovalDecision.PENDING
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
