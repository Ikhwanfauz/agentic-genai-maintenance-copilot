from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text

from app.core.config import get_settings


def normalize_row(row):
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            result[key] = value.astimezone(UTC)
    return result


def main():
    source_path = Path("data/maintenance_copilot.db").resolve()
    if not source_path.is_file():
        raise RuntimeError("SQLite source file not found.")

    target_url = get_settings().database_url
    target_engine = create_engine(target_url, pool_pre_ping=True)
    if target_engine.dialect.name != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL.")

    source_engine = create_engine("sqlite:///file:" + source_path.as_posix() + "?mode=ro&uri=true")

    try:
        source_metadata = MetaData()
        source_metadata.reflect(bind=source_engine)
        target_metadata = MetaData()
        target_metadata.reflect(bind=target_engine)

        expected_tables = {
            "assets",
            "maintenance_records",
            "sensor_readings",
            "work_orders",
            "approvals",
            "agent_runs",
            "agent_steps",
            "tool_calls",
        }
        actual_tables = set(source_metadata.tables) - {"alembic_version"}
        if actual_tables != expected_tables:
            raise RuntimeError("Unexpected SQLite tables; review before migrating.")

        tables = [table for table in source_metadata.sorted_tables if table.name in expected_tables]

        with source_engine.connect() as source, target_engine.begin() as target:
            # Refuse to overwrite any existing application data.
            for table in tables:
                destination = target_metadata.tables[table.name]
                count = target.scalar(select(func.count()).select_from(destination))
                if count:
                    raise RuntimeError(f"Target table {table.name} is not empty. Nothing copied.")

            source_rows = {}
            parent_links = []

            for table in tables:
                destination = target_metadata.tables[table.name]
                rows = [
                    normalize_row(row)
                    for row in source.execute(select(table).order_by(table.c.id)).mappings()
                ]
                source_rows[table.name] = rows

                if set(table.c.keys()) != set(destination.c.keys()):
                    raise RuntimeError(f"Column mismatch: {table.name}")

                # Insert assets first, then restore their parent relationships.
                insert_rows = [dict(row) for row in rows]
                if table.name == "assets":
                    for row in insert_rows:
                        if row["parent_asset_id"] is not None:
                            parent_links.append((row["id"], row["parent_asset_id"]))
                            row["parent_asset_id"] = None

                if insert_rows:
                    target.execute(destination.insert(), insert_rows)

                if table.name == "assets":
                    for asset_id, parent_id in parent_links:
                        target.execute(
                            destination.update()
                            .where(destination.c.id == asset_id)
                            .values(parent_asset_id=parent_id)
                        )

            # Compare every column of every row before committing.
            for table in tables:
                destination = target_metadata.tables[table.name]
                actual = [
                    normalize_row(row)
                    for row in target.execute(
                        select(destination).order_by(destination.c.id)
                    ).mappings()
                ]
                if actual != source_rows[table.name]:
                    raise RuntimeError(f"Data comparison failed: {table.name}")
                print(f"Verified {table.name}: {len(actual)} rows")

            # Advance generated IDs past the imported IDs.
            for table in tables:
                destination = target_metadata.tables[table.name]
                sequence = target.scalar(
                    text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                    {"table_name": table.name},
                )
                if sequence:
                    maximum = target.scalar(select(func.max(destination.c.id)))
                    target.execute(
                        text("SELECT setval(CAST(:sequence AS regclass), :value, :has_rows)"),
                        {
                            "sequence": sequence,
                            "value": maximum if maximum is not None else 1,
                            "has_rows": maximum is not None,
                        },
                    )

        print("Migration committed. All rows verified; SQLite source unchanged.")
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    main()
