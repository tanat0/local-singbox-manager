.PHONY: install run test e2e

VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
ENV_FILE := .env
UVICORN_ENV_FILE := $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)

$(PYTHON):
	python -m venv $(VENV)

install: $(PYTHON)
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(UVICORN) $(UVICORN_ENV_FILE) app.main:app --host 127.0.0.1 --port 9090

test:
	$(VENV)/bin/pytest tests/ --ignore=tests/e2e -v

e2e:
	$(VENV)/bin/pytest tests/e2e --browser chromium -v
