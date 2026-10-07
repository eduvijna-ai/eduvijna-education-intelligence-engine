SHELL := /bin/bash

COMPOSE := docker compose
ifneq ("$(wildcard .env.development)","")
COMPOSE := docker compose --env-file .env.development
endif

.PHONY: setup env dev test lint migrate migration down backend-test frontend-build migration-check source-verify source-help day4-verify day4-verify-official

setup: env
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'
	cd frontend && npm install

env:
	@if [ ! -f .env.development ]; then cp .env.development.example .env.development; fi

dev: env
	$(COMPOSE) up --build

test: backend-test frontend-build migration-check

backend-test:
	$(COMPOSE) run --rm backend pytest

frontend-build:
	$(COMPOSE) run --rm frontend npm run typecheck
	$(COMPOSE) run --rm frontend npm run build

lint:
	$(COMPOSE) run --rm backend ruff check app tests
	$(COMPOSE) run --rm backend mypy app

migrate:
	$(COMPOSE) run --rm backend alembic upgrade head

migration:
	@test -n "$(name)" || (echo "usage: make migration name=description" && exit 1)
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(name)"

migration-check:
	$(COMPOSE) run --rm -e DATABASE_URL=sqlite:////tmp/migration-ci.db backend sh -c 'rm -f /tmp/migration-ci.db && alembic upgrade head && alembic downgrade 20261001_0001 && alembic upgrade head && alembic check'

down:
	$(COMPOSE) down

source-verify:
	$(COMPOSE) run --rm backend python -m app.source_verify

source-help:
	$(COMPOSE) run --rm backend python -m app.source_cli --help

day4-verify:
	$(COMPOSE) run --rm backend python -m app.day4_verify

day4-verify-official:
	$(COMPOSE) run --rm backend python -m app.day4_verify --fetch-official

.PHONY: day5-verify day5-verify-official
day5-verify:
	$(COMPOSE) run --rm backend python -m app.day5_verify

day5-verify-official:
	$(COMPOSE) run --rm backend python -m app.day5_verify --fetch-official
