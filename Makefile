PYTHON ?= python3.12
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: install lint test fmt up down test-integration smoke deploy seed scenarios backup restore logs ps

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	# runtime versions = the ones in the registrar image
	$(BIN)/pip install -c deploy/registrar/requirements.lock -e '.[dev]'

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests
	$(BIN)/mypy

# Coverage gates (SPEC §14): core/ + services/ >= 90%, dns/projector.py 100% of branches.
COV := --cov=plot.core --cov=plot.services --cov=plot.dns.projector --cov-branch \
	--cov-report=term-missing:skip-covered --cov-fail-under=90

test:
	$(BIN)/pytest -m "not integration" $(COV)
	$(BIN)/coverage report --include='*/plot/dns/projector.py' --fail-under=100

fmt:
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests

# Docker Compose stack (SPEC §4.1). ENV_FILE holds BIND_ADDR, API_KEY, PDNS_API_KEY, ...
ENV_FILE ?= .env
COMPOSE := docker compose --env-file $(ENV_FILE) --project-directory . -f deploy/docker-compose.yml

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

# Needs the stack from `make up`; talks to it through BIND_ADDR from ENV_FILE and runs the
# scenario catalog inside the registrar container.
test-integration:
	PLOT_ENV_FILE=$(ENV_FILE) $(BIN)/pytest -m integration tests/integration tests/scenarios -v

# One command on a fresh clone: preflight, build, start, wait healthy, seed, smoke.
deploy:
	ENV_FILE=$(ENV_FILE) scripts/deploy.sh

# Quick outside-in check of the running stack (health, NXDOMAIN, passthrough, registry, seed).
smoke:
	ENV_FILE=$(ENV_FILE) scripts/smoke.sh

# Provider domain myhost.net (NS1_IP/NS2_IP override the demo-ns addresses).
seed:
	$(COMPOSE) exec -T registrar plot seed provider $(if $(NS1_IP),--ns1-ip $(NS1_IP)) $(if $(NS2_IP),--ns2-ip $(NS2_IP))

scenarios:
	$(COMPOSE) exec -T registrar plot scenario run --all

# Online backup into DATA_DIR/backups/; restore with `make restore FILE=<backup>`.
backup:
	$(COMPOSE) exec -T registrar python -m plot.db.backup /data/registrar.db /data/backups

restore:
	ENV_FILE=$(ENV_FILE) scripts/restore.sh $(FILE)

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps
