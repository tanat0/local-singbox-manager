.PHONY: install dev-install lock lock-check export-requirements run lint test e2e check-fast check install-hooks doctor telegram-check

VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
PYTHON := $(shell test -x "$(VENV_PYTHON)" && echo "$(VENV_PYTHON)" || command -v python3 || command -v python)
RUFF := $(shell test -x "$(VENV)/bin/ruff" && echo "$(VENV)/bin/ruff" || command -v ruff)
PYTEST := $(shell test -x "$(VENV)/bin/pytest" && echo "$(VENV)/bin/pytest" || command -v pytest)
UVICORN := $(shell test -x "$(VENV)/bin/uvicorn" && echo "$(VENV)/bin/uvicorn" || command -v uvicorn)
ENV_FILE := .env
UVICORN_ENV_FILE := $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)

$(VENV_PYTHON):
	uv sync --no-dev

install:
	uv sync --no-dev

dev-install:
	uv sync --group dev

lock:
	uv lock

lock-check:
	uv lock --check

export-requirements:
	uv export --no-dev --no-hashes --no-emit-project --output-file requirements.txt
	uv export --group dev --no-hashes --no-emit-project --output-file requirements-dev.txt

run:
	$(UVICORN) $(UVICORN_ENV_FILE) app.main:app --host 127.0.0.1 --port 9090

lint:
	$(RUFF) check app tests scripts migrations

test:
	$(PYTEST) tests/ --ignore=tests/e2e -v

e2e:
	$(PYTEST) tests/e2e --browser chromium -v

check-fast: lint test

check: lint test e2e

install-hooks:
	chmod +x tools/githooks/*
	git config core.hooksPath tools/githooks

doctor:
	@echo "Python: $$(python --version 2>/dev/null || true)"
	@echo "Selected python: $(PYTHON)"
	@echo "Venv: $$(test -x "$(VENV_PYTHON)" && echo ok || echo missing)"
	@echo "Hooks path: $$(git config --get core.hooksPath || echo default)"
	@echo "Ruff: $$($(RUFF) --version 2>/dev/null || echo missing)"
	@echo "Pytest: $$($(PYTEST) --version 2>/dev/null || echo missing)"
	@echo "Playwright: $$($(PYTHON) -c 'import playwright; print("ok")' 2>/dev/null || echo missing)"

telegram-check:
	$(PYTHON) scripts/check-telegram.py
