"""Consistent online backup of the registrar database (``make backup``).

Usage: ``python -m plot.db.backup DATABASE BACKUP_DIR`` — prints the backup file path.
Uses SQLite's backup API, so it is safe while the registrar is writing (WAL mode).
"""

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def backup(database: Path, directory: Path, now: datetime | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"registrar-{stamp}.db"
    source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        with sqlite3.connect(target) as copy:
            source.backup(copy)
        copy.close()
    finally:
        source.close()
    return target


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("usage: python -m plot.db.backup DATABASE BACKUP_DIR\n")
        return 2
    sys.stdout.write(f"{backup(Path(argv[1]), Path(argv[2]))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
