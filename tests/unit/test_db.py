import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from plot.db.models import Base, Domain, DomainStatus, Host, HostAddr
from plot.db.session import (
    alembic_config,
    make_engine,
    make_session_factory,
    migrate,
    sqlite_url,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _domain(name: str = "shop.com") -> Domain:
    return Domain(
        name=name,
        suffix="com",
        label=name.split(".")[0],
        owner="alice",
        auth_code="x",
        created_at=T0,
        expires_at=T0 + timedelta(days=365),
        updated_at=T0,
    )


def test_migration_matches_models() -> None:
    engine = make_engine("sqlite://")
    migrate(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "domains",
        "domain_statuses",
        "hosts",
        "host_addrs",
        "domain_ns",
        "events",
        "pending_changes",
        "published_state",
        "settings",
    }


def test_migration_downgrades_to_empty() -> None:
    engine = make_engine("sqlite://")
    migrate(engine)
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}


def test_migrate_file_database(tmp_path: Path) -> None:
    engine = make_engine(sqlite_url(tmp_path))
    migrate(engine)
    migrate(engine)  # idempotent
    assert (tmp_path / "registrar.db").exists()


def test_timestamps_roundtrip_as_utc_iso_text() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    bangkok = timezone(timedelta(hours=7))
    with sessions.begin() as session:
        domain = _domain()
        domain.created_at = datetime(2026, 1, 1, 7, 0, tzinfo=bangkok)
        session.add(domain)
    with engine.connect() as connection:
        raw = connection.execute(text("SELECT created_at FROM domains")).scalar_one()
    assert raw == "2026-01-01T00:00:00.000000Z"
    with sessions() as session:
        loaded = session.scalars(select(Domain)).one()
        assert loaded.created_at == T0
        assert loaded.created_at.tzinfo is UTC


def test_naive_timestamp_is_rejected() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        domain = _domain()
        domain.created_at = datetime(2026, 1, 1)
        session.add(domain)
        with pytest.raises(StatementError):
            session.flush()


def test_foreign_keys_cascade_and_constraints() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    with sessions.begin() as session:
        domain = _domain()
        session.add(domain)
        session.flush()
        session.add(DomainStatus(domain_id=domain.id, status="clientHold"))
        host = Host(
            name="ns1.shop.com", kind="subordinate", parent_domain_id=domain.id, created_at=T0
        )
        host.addrs.append(HostAddr(address="192.168.1.10", family=4))
        session.add(host)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM domains"))
        for table in ("domain_statuses", "hosts", "host_addrs"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
    with sessions() as session:
        domain = _domain()
        session.add(domain)
        session.flush()
        session.add(DomainStatus(domain_id=domain.id, status="ok"))
        with pytest.raises(IntegrityError):
            session.flush()


def test_file_database_uses_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = make_engine(sqlite_url(tmp_path))
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 10000
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_concurrent_writers_wait_instead_of_failing(tmp_path: Path) -> None:
    engine = make_engine(sqlite_url(tmp_path))
    migrate(engine)
    sessions = make_session_factory(engine)
    errors: list[Exception] = []

    def writer(prefix: str) -> None:
        try:
            for n in range(20):
                with sessions.begin() as session:
                    session.add(_domain(f"{prefix}{n}.com"))
        except Exception as err:  # pragma: no cover - only on failure
            errors.append(err)

    threads = [threading.Thread(target=writer, args=(p,)) for p in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with sessions() as session:
        assert session.query(Domain).count() == 60
