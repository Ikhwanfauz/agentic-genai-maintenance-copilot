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
