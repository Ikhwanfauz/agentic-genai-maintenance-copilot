from app.schemas.asset import AssetDetailsInput, AssetDetailsOutput
from app.schemas.common import AssetCodeInput
from app.schemas.maintenance import (
    MaintenanceHistoryInput,
    MaintenanceHistoryOutput,
    MaintenanceRecordOutput,
)
from app.schemas.sensor import (
    DataQualitySummary,
    SensorAnalysisInput,
    SensorAnalysisOutput,
    SensorMetricOutput,
    TrendDirection,
)

__all__ = [
    "AssetCodeInput",
    "AssetDetailsInput",
    "AssetDetailsOutput",
    "DataQualitySummary",
    "MaintenanceHistoryInput",
    "MaintenanceHistoryOutput",
    "MaintenanceRecordOutput",
    "SensorAnalysisInput",
    "SensorAnalysisOutput",
    "SensorMetricOutput",
    "TrendDirection",
]
