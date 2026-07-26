.PHONY: help install test lint typecheck check fmt up down migrate revision seed

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install project + dev deps
	uv venv --python 3.11
	uv pip install -e ".[dev]"

test: ## Run the test suite
	.venv/bin/python -m pytest

lint: ## Lint with ruff
	.venv/bin/ruff check packages tests

fmt: ## Auto-fix lint + format
	.venv/bin/ruff check --fix packages tests
	.venv/bin/ruff format packages tests

typecheck: ## Static type check
	.venv/bin/mypy packages

check: lint test ## Lint + test (the CI fast gate)

up: ## Start the local infra stack (Postgres+AGE, Redis, MinIO, OpenSearch)
	docker compose up -d

down: ## Stop the local infra stack
	docker compose down

migrate: ## Apply DB migrations to head
	.venv/bin/alembic -c alembic.ini upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	.venv/bin/alembic -c alembic.ini revision --autogenerate -m "$(m)"
