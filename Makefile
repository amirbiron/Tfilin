.PHONY: help install install-dev test lint format type-check clean run docker-build docker-run

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: ## Install development dependencies
	pip install -r requirements-dev.txt

test: ## Run tests with coverage
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

test-fast: ## Run tests without coverage
	pytest tests/ -v

lint: ## Run linting checks
	flake8 .
	isort --check-only --diff .
	black --check .

format: ## Format code with black and isort
	isort .
	black .

type-check: ## Run type checking with mypy
	mypy --ignore-missing-imports --no-strict-optional .

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true

run: ## Run the bot locally
	python main_updated.py

docker-build: ## Build Docker image
	docker build -t tefillin-bot:latest .

docker-run: ## Run bot in Docker container
	docker run --rm -it \
		--env-file .env \
		tefillin-bot:latest

ci: lint type-check test ## Run all CI checks

pre-commit: format lint type-check test ## Run all checks before committing