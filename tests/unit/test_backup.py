import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plot.db import backup
from plot.db.session import make_engine, migrate, sqlite_url


def test_backup_is_consistent_copy_of_live_wal_database(tmp_path: Path) -> None:
    engine = make_engine(sqlite_url(tmp_path))  # WAL mode, connection stays open
    migrate(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO settings (key, value) VALUES ('ns_ttl', '60')")
    target = backup.backup(
        tmp_path / "registrar.db", tmp_path / "backups", datetime(2026, 10, 23, 1, 2, 3, tzinfo=UTC)
    )
    assert target == tmp_path / "backups" / "registrar-20261023T010203Z.db"
    with sqlite3.connect(target) as copy:
        assert copy.execute("SELECT value FROM settings WHERE key='ns_ttl'").fetchone() == (60,)
    engine.dispose()


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sqlite3.connect(tmp_path / "x.db").close()
    assert backup.main(["backup", str(tmp_path / "x.db"), str(tmp_path / "out")]) == 0
    assert capsys.readouterr().out.strip().startswith(str(tmp_path / "out" / "registrar-"))
    assert backup.main(["backup"]) == 2
