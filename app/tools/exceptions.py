class ToolError(Exception):
    """Base exception for deterministic maintenance tools."""


class AssetNotFoundError(ToolError):
    def __init__(self, asset_code: str) -> None:
        self.asset_code = asset_code
        super().__init__(f"Asset '{asset_code}' was not found.")


class SensorDataNotFoundError(ToolError):
    def __init__(self, asset_code: str) -> None:
        self.asset_code = asset_code
        super().__init__(
            f"No sensor readings were found for asset '{asset_code}' and the requested filters."
        )
