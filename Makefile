SHELL := /bin/bash

.PHONY: setup dev test lint migrate migration down backend-test frontend-build migration-check

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'
	cd frontend && npm install

dev:
	docker compose up --build

test: backend-test frontend-build migration-check

backend-test:
	docker compose run --rm backend pytest

frontend-build:
	docker compose run --rm frontend npm run typecheck
	docker compose run --rm frontend npm run build

lint:
	docker compose run --rm backend ruff check app tests
	docker compose run --rm backend mypy app

migrate:
	docker compose run --rm backend alembic upgrade head

migration:
	@test -n "$(name)" || (echo "usage: make migration name=description" && exit 1)
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(name)"

migration-check:
	docker compose run --rm -e DATABASE_URL=sqlite:////tmp/migration-ci.db backend sh -c 'rm -f /tmp/migration-ci.db && alembic upgrade head && alembic downgrade 20261001_0001 && alembic upgrade head'

down:
	docker compose down
