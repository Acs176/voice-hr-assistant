.PHONY: install test lint format run

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
