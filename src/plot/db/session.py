"""Engine/session factories and schema migration."""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

DB_FILENAME = "registrar.db"


def sqlite_url(data_dir: Path) -> str:
    return f"sqlite:///{data_dir / DB_FILENAME}"


def make_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection so every session sees the same in-memory database.
        kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    engine = create_engine(url, **kwargs)
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "plot.db:migrations")
    return config


def migrate(engine: Engine) -> None:
    """Upgrade the database schema to the latest revision."""
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
