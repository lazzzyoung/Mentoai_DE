.PHONY: up down logs ps migrate seed pipeline test lint fmt check

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

ps:
	docker compose ps

migrate:
	uv run mentoai migrate

seed:
	uv run mentoai seed

pipeline:
	uv run mentoai pipeline

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests && uv run ruff check --fix src tests

check: lint
	uv run ty check src
	uv run pytest -q
