UV ?= uv
export UV_CACHE_DIR ?= $(CURDIR)/.uv-cache

.PHONY: install test lint format build schema smoke-wheel check
install:
	$(UV) sync --locked
test:
	$(UV) run --locked pytest
lint:
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
format:
	$(UV) run --locked ruff format .
	$(UV) run --locked ruff check --fix .
build:
	$(UV) build
schema:
	$(UV) run --locked python scripts/export_schema.py
smoke-wheel: build
	$(UV) run --locked python scripts/smoke_wheel.py --uv $(UV)
check: lint test build
