import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Maintenance Copilot")


@mcp.tool()
def get_last_service(asset_code: str) -> dict[str, Any]:
    """Get the latest maintenance record for an asset such as P-101."""
    asset_code = asset_code.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]*-[0-9]{3}", asset_code):
        raise ValueError("Enter an asset code such as P-101.")

    url = f"http://127.0.0.1:8000/assets/{asset_code}/last-service"
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
    except httpx.RequestError as exc:
        raise RuntimeError("Could not reach the local Maintenance Copilot API.") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Maintenance Copilot API returned HTTP {exc.response.status_code} "
            f"for asset {asset_code}."
        ) from exc

    return response.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
