from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.asset import Asset
from app.schemas.asset import AssetDetailsInput, AssetDetailsOutput
from app.tools.exceptions import AssetNotFoundError


def get_asset_details(
    database_session: Session,
    tool_input: AssetDetailsInput,
) -> AssetDetailsOutput:
    statement = (
        select(Asset)
        .where(Asset.asset_code == tool_input.asset_code)
        .options(
            selectinload(Asset.parent),
            selectinload(Asset.children),
        )
    )

    asset = database_session.scalar(statement)

    if asset is None:
        raise AssetNotFoundError(tool_input.asset_code)

    return AssetDetailsOutput(
        id=asset.id,
        asset_code=asset.asset_code,
        name=asset.name,
        asset_type=asset.asset_type,
        status=asset.status,
        criticality=asset.criticality,
        location=asset.location,
        manufacturer=asset.manufacturer,
        model_number=asset.model_number,
        installation_date=asset.installation_date,
        description=asset.description,
        parent_asset_code=(asset.parent.asset_code if asset.parent is not None else None),
        child_asset_codes=sorted(child.asset_code for child in asset.children),
    )
