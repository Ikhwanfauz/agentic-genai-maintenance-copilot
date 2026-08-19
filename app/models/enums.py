from enum import StrEnum


class AssetType(StrEnum):
    PUMP = "pump"
    MOTOR = "motor"


class AssetStatus(StrEnum):
    OPERATIONAL = "operational"
    STANDBY = "standby"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SensorType(StrEnum):
    VIBRATION = "vibration"
    TEMPERATURE = "temperature"
    SUCTION_PRESSURE = "suction_pressure"
    DISCHARGE_PRESSURE = "discharge_pressure"
    FLOW_RATE = "flow_rate"
    MOTOR_CURRENT = "motor_current"


class DataQuality(StrEnum):
    GOOD = "good"
    SUSPECT = "suspect"
    BAD = "bad"


class MaintenanceType(StrEnum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"
    INSPECTION = "inspection"


class WorkOrderPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkOrderStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class ApprovalDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"


class AgentStepType(StrEnum):
    ROUTING = "routing"
    TOOL_SELECTION = "tool_selection"
    TOOL_EXECUTION = "tool_execution"
    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    GUARDRAIL = "guardrail"
    APPROVAL_PAUSE = "approval_pause"
    FINAL_RESPONSE = "final_response"


class AgentStepStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolCallStatus(StrEnum):
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
