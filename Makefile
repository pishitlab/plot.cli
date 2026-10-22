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

# Coverage gate for core/ and services/ (SPEC §14: >= 90%).
COV := --cov=plot.core --cov=plot.services --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=90

test:
	$(BIN)/pytest -m "not integration" $(COV)

fmt:
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests
