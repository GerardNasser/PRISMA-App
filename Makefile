.PHONY: help dev up down api web test lint typecheck migrate clean

help:
	@echo "Targets:"
	@echo "  up         start full stack via docker compose"
	@echo "  down       stop the stack"
	@echo "  api        run api locally (no docker)"
	@echo "  web        run web locally (no docker)"
	@echo "  test       run all backend tests"
	@echo "  lint       ruff + eslint"
	@echo "  typecheck  mypy + tsc"
	@echo "  migrate    apply alembic migrations"
	@echo "  fields-validate  validate all field config YAMLs against schema"

up:
	docker compose up --build

down:
	docker compose down

api:
	cd apps/api && uv run uvicorn prismapi.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd apps/web && npm run dev

test:
	cd apps/api && uv run pytest -q

lint:
	cd apps/api && uv run ruff check src tests
	cd apps/web && npm run lint || true

typecheck:
	cd apps/api && uv run mypy src

migrate:
	cd apps/api && uv run alembic upgrade head

fields-validate:
	cd apps/api && uv run python -m prismapi.fields.validate

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
