class WorkOrderServiceError(Exception):
    """Base exception for deterministic work-order services."""


class WorkOrderAssetNotFoundError(WorkOrderServiceError):
    def __init__(self, asset_code: str) -> None:
        self.asset_code = asset_code
        super().__init__(f"Asset '{asset_code}' was not found for work-order proposal.")


class WorkOrderIdempotencyConflictError(WorkOrderServiceError):
    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(
            "Idempotency key "
            f"'{idempotency_key}' is already associated with "
            "a different work-order proposal."
        )


class WorkOrderProposalStateError(WorkOrderServiceError):
    pass


class WorkOrderPersistenceError(WorkOrderServiceError):
    pass


class WorkOrderNotFoundError(WorkOrderServiceError):
    def __init__(self, work_order_id: int) -> None:
        self.work_order_id = work_order_id
        super().__init__(f"Work order '{work_order_id}' was not found.")


class WorkOrderApprovalNotFoundError(WorkOrderServiceError):
    def __init__(
        self,
        work_order_id: int,
        request_version: int,
    ) -> None:
        self.work_order_id = work_order_id
        self.request_version = request_version
        super().__init__(
            "Approval request for work order "
            f"'{work_order_id}' version '{request_version}' was not found."
        )


class WorkOrderApprovalVersionConflictError(WorkOrderServiceError):
    def __init__(
        self,
        requested_version: int,
        current_version: int,
    ) -> None:
        self.requested_version = requested_version
        self.current_version = current_version
        super().__init__(
            "Approval request version "
            f"'{requested_version}' does not match current work-order "
            f"revision '{current_version}'."
        )


class WorkOrderApprovalStateError(WorkOrderServiceError):
    pass


class WorkOrderApprovalConflictError(WorkOrderServiceError):
    pass


class WorkOrderApprovalExpiredError(WorkOrderServiceError):
    def __init__(
        self,
        work_order_id: int,
        request_version: int,
    ) -> None:
        self.work_order_id = work_order_id
        self.request_version = request_version
        super().__init__(
            "Approval request for work order "
            f"'{work_order_id}' version '{request_version}' has expired."
        )


class AgentWorkflowServiceError(Exception):
    """Base exception for agent workflow application services."""


class AgentRunNotFoundError(AgentWorkflowServiceError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Agent run '{run_id}' was not found.")


class AgentWorkflowStateError(AgentWorkflowServiceError):
    pass


class AgentWorkflowExecutionError(AgentWorkflowServiceError):
    def __init__(
        self,
        run_id: str,
        message: str,
    ) -> None:
        self.run_id = run_id
        super().__init__(message)


class AgentWorkflowPersistenceError(AgentWorkflowServiceError):
    pass
