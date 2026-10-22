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

test:
	$(BIN)/pytest -m "not integration"

fmt:
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests
