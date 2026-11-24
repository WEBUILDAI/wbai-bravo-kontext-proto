# WBAI-Standard-Makefile. `make verify` ist das Gate für CI und Stop-Hook.
PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
REQ_FILES := requirements-dev.txt infra/requirements.txt

.PHONY: help venv install compile lint format format-check test verify preview clean

help: ## Zeigt diese Hilfe
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

venv: $(BIN)/python ## Legt das virtuelle Environment an

install: venv ## Installiert alle gepinnten Abhängigkeiten und pre-commit-Hooks
	$(BIN)/pip install $(addprefix -r ,$(REQ_FILES))
	-$(BIN)/pre-commit install

compile: venv ## Pinnt requirements*.in nach requirements*.txt (pip-tools)
	$(BIN)/pip install pip-tools
	$(BIN)/pip-compile --quiet --strip-extras --output-file requirements-dev.txt requirements-dev.in
	$(BIN)/pip-compile --quiet --strip-extras --output-file infra/requirements.txt infra/requirements.in

lint: ## Ruff-Lint
	$(BIN)/ruff check .

format: ## Formatiert mit Black und Ruff-Fixes
	$(BIN)/black .
	$(BIN)/ruff check --fix .

format-check: ## Prüft die Formatierung ohne zu ändern
	$(BIN)/black --check .

test: ## Führt die Tests aus
	$(BIN)/pytest

verify: lint format-check test ## Gate: Lint, Format, Tests

preview: ## pulumi preview für Stack proto (nur lokal, braucht Azure-Login)
	cd infra && pulumi preview --stack proto

clean: ## Entfernt Caches
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
