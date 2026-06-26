.PHONY: install test lint format run langfuse langfuse-down

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run mypy

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

run:
	uv run cs-voice dev

langfuse:  # local Langfuse for tracing; UI at http://localhost:3000
	docker compose -f docker-compose.langfuse.yml up -d

langfuse-down:  # stop the local Langfuse stack (add `-v` manually to wipe its data)
	docker compose -f docker-compose.langfuse.yml down
