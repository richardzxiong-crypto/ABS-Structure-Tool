# ABS Structuring Tool
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: setup test run-api run-ui dev clean

setup:  ## create venv, install backend + frontend deps
	cd $(BACKEND) && uv venv .venv && uv pip install -e ".[dev]"
	cd $(FRONTEND) && npm install

test:  ## run the backend test suite
	cd $(BACKEND) && .venv/bin/python -m pytest -q

run-api:  ## FastAPI on :8000
	cd $(BACKEND) && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

run-ui:  ## Vite dev server on :5173 (proxies /api to :8000)
	cd $(FRONTEND) && npm run dev

dev:  ## run API + UI together
	$(MAKE) -j2 run-api run-ui

clean:
	rm -rf $(BACKEND)/.venv $(FRONTEND)/node_modules $(FRONTEND)/dist
