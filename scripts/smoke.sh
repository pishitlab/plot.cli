#!/usr/bin/env bash
# Outside-in check of the running stack (`make smoke`). Runs in a throwaway registrar
# container on the host network, so the server needs no Python of its own.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=${ENV_FILE:-.env}
value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }
docker run --rm --network host \
    -e BIND_ADDR="$(value BIND_ADDR)" -e API_KEY="$(value API_KEY)" \
    plot-registrar:local python -m plot.smoke
