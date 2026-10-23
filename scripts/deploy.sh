#!/usr/bin/env bash
# One-command deploy (`make deploy`): preflight -> build -> start -> wait healthy -> seed -> smoke.
# Safe to re-run: keeps an existing .env, rebuilds images, seeding is idempotent.
#
# Environment:
#   ENV_FILE      env file to use/create (default .env)
#   BIND_ADDR     used only when the env file is created (default: value in .env.example)
#   NS1_IP NS2_IP addresses for `plot seed provider` (default: demo-ns 172.28.0.31/.32)
#   SKIP_BUILD=1  start with already built images (no `--build`)
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=${ENV_FILE:-.env}
COMPOSE=(docker compose --env-file "$ENV_FILE" --project-directory . -f deploy/docker-compose.yml)

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }
random_key() { od -An -tx1 -N24 /dev/urandom | tr -d ' \n'; }

say "Preflight"
for tool in curl od timeout; do command -v "$tool" >/dev/null || fail "$tool is required (sudo apt install curl coreutils)"; done
command -v docker >/dev/null || fail "docker is not installed (https://docs.docker.com/engine/install/)"
docker info >/dev/null 2>&1 || fail "cannot talk to the Docker daemon (is it running? are you in the docker group?)"
compose_version=$(docker compose version --short 2>/dev/null) || fail "the Docker Compose plugin (v2) is missing"
[ "${compose_version%%.*}" -ge 2 ] 2>/dev/null || fail "Docker Compose v2 is required, found $compose_version"
echo "docker $(docker version --format '{{.Server.Version}}'), compose $compose_version"

if [ ! -f "$ENV_FILE" ]; then
    umask 077
    sed -e "s/^API_KEY=.*/API_KEY=$(random_key)/" \
        -e "s/^PDNS_API_KEY=.*/PDNS_API_KEY=$(random_key)/" \
        ${BIND_ADDR:+-e "s/^BIND_ADDR=.*/BIND_ADDR=$BIND_ADDR/"} \
        .env.example > "$ENV_FILE"
    echo "created $ENV_FILE with random API keys (mode 600)"
fi
chmod 600 "$ENV_FILE"

bind=$(env_value BIND_ADDR)
if [ -n "${BIND_ADDR:-}" ] && [ "$BIND_ADDR" != "$bind" ]; then
    fail "BIND_ADDR=$BIND_ADDR was given but $ENV_FILE already says BIND_ADDR=$bind; edit $ENV_FILE instead"
fi
api_key=$(env_value API_KEY)
pdns_key=$(env_value PDNS_API_KEY)
for pair in "API_KEY:$api_key" "PDNS_API_KEY:$pdns_key"; do
    name=${pair%%:*} value=${pair#*:}
    [ -n "$value" ] || fail "$name is empty in $ENV_FILE"
    [ "$value" != "change-me" ] || fail "$name is still 'change-me' in $ENV_FILE"
    [ ${#value} -ge 16 ] || fail "$name in $ENV_FILE is shorter than 16 characters"
done
[ -n "$bind" ] || fail "BIND_ADDR is empty in $ENV_FILE"
[ "$bind" != "0.0.0.0" ] || fail "BIND_ADDR=0.0.0.0 would publish DNS and the API on every interface (N10)"
local_addresses() {
    if command -v ip >/dev/null; then
        ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1
    elif hostname -I >/dev/null 2>&1; then
        hostname -I | tr ' ' '\n'
        echo 127.0.0.1
    fi
}
addresses=$(local_addresses)
if [ -z "$addresses" ]; then
    echo "warning: cannot list local addresses (no ip/hostname -I); Docker will refuse a wrong BIND_ADDR"
elif ! printf '%s\n' "$addresses" | grep -qx "$bind"; then
    fail "BIND_ADDR=$bind is not an address of this machine (found: $(echo $addresses))"
fi

# Ports must be free before the first start (later runs find our own containers on them).
tcp_listening() { timeout 2 bash -c ": >/dev/tcp/$1/$2" 2>/dev/null; }
udp_listening() {  # 0 = in use, 1 = free, 2 = cannot tell
    local pattern="^($bind|0\.0\.0\.0|\*|\[::\]|::):$1$"
    if command -v ss >/dev/null; then
        ss -Hlnu "sport = :$1" | awk '{print $4}' | grep -Eq "$pattern" && return 0
        return 1
    elif command -v lsof >/dev/null && [ "$(id -u)" = 0 ]; then
        lsof -nP -iUDP:"$1" | awk 'NR > 1 {print $9}' | grep -Eq "$pattern" && return 0
        return 1
    fi
    return 2
}
running=$("${COMPOSE[@]}" ps -q 2>/dev/null || true)
if [ -z "$running" ]; then
    for port in 53 5300 8080; do
        if tcp_listening "$bind" "$port"; then
            fail "tcp/$port is already in use on $bind; stop that service or pick another BIND_ADDR (RUNBOOK §1.3)"
        fi
    done
    for port in 53 5300; do
        if udp_listening "$port"; then
            fail "udp/$port is already in use on $bind; stop that service or pick another BIND_ADDR (RUNBOOK §1.3)"
        elif [ $? = 2 ]; then
            echo "warning: cannot check udp/$port (no ss, lsof needs root); 'docker compose up' fails if it is taken"
        fi
    done
fi
data_dir=$(env_value DATA_DIR); data_dir=${data_dir:-./data}
mkdir -p "$data_dir"
echo "BIND_ADDR=$bind, DATA_DIR=$data_dir: ok"

say "Build and start"
if [ "${SKIP_BUILD:-0}" = 1 ]; then
    "${COMPOSE[@]}" up -d --no-build
else
    "${COMPOSE[@]}" up -d --build
fi

say "Wait until the registrar reports healthy"
health=""
for _ in $(seq 1 90); do
    health=$(curl -fsS --max-time 3 "http://$bind:8080/api/v1/health" 2>/dev/null || true)
    case "$health" in *'"status":"ok"'*) break ;; esac
    sleep 2
done
case "$health" in
    *'"status":"ok"'*) echo "$health" ;;
    *) "${COMPOSE[@]}" ps; "${COMPOSE[@]}" logs --tail=40; fail "not healthy after 3 minutes: ${health:-no answer}" ;;
esac

say "Seed the provider domain"
seed_args=()
[ -n "${NS1_IP:-}" ] && seed_args+=(--ns1-ip "$NS1_IP")
[ -n "${NS2_IP:-}" ] && seed_args+=(--ns2-ip "$NS2_IP")
"${COMPOSE[@]}" exec -T registrar plot seed provider "${seed_args[@]}"

say "Smoke test"
ENV_FILE="$ENV_FILE" scripts/smoke.sh

say "Done"
cat <<DONE
  API     http://$bind:8080/api/v1/health
  Web UI  http://$bind:8080/ui/   (log in with API_KEY from $ENV_FILE)
  DNS     point clients at $bind (docs/RUNBOOK.md §3)
DONE
