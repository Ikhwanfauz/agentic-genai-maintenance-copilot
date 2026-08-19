from sqlalchemy import text

from app.db.session import create_database_engine


def test_sqlite_connection_and_foreign_keys() -> None:
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        with test_engine.connect() as connection:
            database_response = connection.scalar(text("SELECT 1"))
            foreign_keys_enabled = connection.scalar(text("PRAGMA foreign_keys"))

        assert database_response == 1
        assert foreign_keys_enabled == 1
    finally:
        test_engine.dispose()
