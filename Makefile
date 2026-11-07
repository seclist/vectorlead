.PHONY: help install dev test test-cov lint format clean hunt stats

help:
	@echo "VectorLead Development Commands:"
	@echo "  make install     - Install package in editable mode"
	@echo "  make dev         - Install package with dev and test dependencies"
	@echo "  make test        - Run pytest test suite"
	@echo "  make test-cov    - Run pytest with terminal coverage report"
	@echo "  make lint        - Run ruff linter check"
	@echo "  make format      - Auto-format code using ruff"
	@echo "  make hunt        - Run discovery quota batch for personal_trainer"
	@echo "  make stats       - Display SQLite and CRM pipeline metrics"
	@echo "  make clean       - Clean temporary build, cache, and pytest files"

install:
	pip install -e .

dev:
	pip install -e .[dev]

test:
	pytest -v

test-cov:
	pytest --cov=src --cov-report=term-missing tests/

lint:
	ruff check .

format:
	ruff check --fix .

hunt:
	python main.py hunt --niche personal_trainer --min-new-leads 10

stats:
	python main.py stats

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache build dist *.egg-info
