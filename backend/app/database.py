from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings


def enable_sqlite_foreign_keys(database_engine: Engine) -> None:
    """Enable SQLite FK enforcement wherever the SQL adapter is configured."""
    if database_engine.dialect.name != "sqlite":
        return

    @event.listens_for(database_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)
enable_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)
