from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import create_database_engine
from app.models import Asset, MaintenanceRecord, SensorReading


def test_core_industrial_tables_can_be_created() -> None:
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        Base.metadata.create_all(test_engine)
        database_inspector = inspect(test_engine)

        table_names = set(database_inspector.get_table_names())

        assert {
            Asset.__tablename__,
            SensorReading.__tablename__,
            MaintenanceRecord.__tablename__,
        }.issubset(table_names)

        sensor_foreign_keys = database_inspector.get_foreign_keys(SensorReading.__tablename__)
        maintenance_foreign_keys = database_inspector.get_foreign_keys(
            MaintenanceRecord.__tablename__
        )

        assert sensor_foreign_keys[0]["referred_table"] == Asset.__tablename__
        assert maintenance_foreign_keys[0]["referred_table"] == Asset.__tablename__
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
