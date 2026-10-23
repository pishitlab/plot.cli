PYTHON ?= python3.12
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: install lint test fmt

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e '.[dev]'

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
