#!/usr/bin/env bash
# Restore the registrar database from a backup (`make restore FILE=...`).
# 1. the backup must pass `PRAGMA integrity_check` (checked before anything is stopped);
# 2. the registrar is stopped, the WAL side files are removed (they belong to the old
#    database) and the backup is copied in;
# 3. the registrar starts and reconciles zone "." from the restored database.
# File work runs in a throwaway registrar container: DATA_DIR is written by the containers
# (root), so it needs no sudo on the host.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=${ENV_FILE:-.env}
FILE=${1:?usage: scripts/restore.sh BACKUP_FILE}
[ -f "$FILE" ] || { echo "no such file: $FILE" >&2; exit 1; }
backup=$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")
COMPOSE=(docker compose --env-file "$ENV_FILE" --project-directory . -f deploy/docker-compose.yml)
data_dir=$(sed -n 's/^DATA_DIR=//p' "$ENV_FILE" | tail -n 1)
data_dir=$(cd "${data_dir:-./data}" && pwd)
in_container() {
    docker run --rm --network none -v "$data_dir:/data" -v "$backup:/restore.db:ro" \
        --entrypoint python plot-registrar:local -c "$1"
}

in_container "
import sqlite3, sys
result = sqlite3.connect('file:/restore.db?mode=ro', uri=True).execute('PRAGMA integrity_check').fetchone()[0]
sys.exit(0 if result == 'ok' else 'backup failed PRAGMA integrity_check: ' + result)
"
"${COMPOSE[@]}" stop registrar
in_container "
import pathlib, shutil
for side in ('-wal', '-shm'):
    pathlib.Path('/data/registrar.db' + side).unlink(missing_ok=True)
shutil.copyfile('/restore.db', '/data/registrar.db')
"
"${COMPOSE[@]}" up -d --no-build --wait registrar
echo "restored $FILE; the registrar reconciled DNS from it on start (make logs)"
