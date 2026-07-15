.PHONY: install lint format typecheck check fix clean

install:
	uv sync

lint:
	uv run ruff check

format:
	uv run ruff format

typecheck:
	uv run pyright

check: lint format-check typecheck

format-check:
	uv run ruff format --check

fix:
	uv run ruff check --fix
	uv run ruff format

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .ruff_cache .pyright_cache
