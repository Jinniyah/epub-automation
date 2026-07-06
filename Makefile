# -----------------------------
# Virtual environment
# -----------------------------
# Toolchain targets ported from epub-renamer (github.com/Jinniyah/
# epub-renamer), per docs/requirements/09-testing-strategy.md
# "Backend: reuse the existing toolchain, don't invent a new one".
# `coverage` is the one target not present there -- added new for the
# 80%-floor CI gate (docs/BACKLOG.md Epic 0).

venv:
	python -m venv .venv

activate:
	@echo "To activate your virtual environment:"
	@echo "  PowerShell:  .\.venv\Scripts\Activate.ps1"
	@echo "  CMD:         .\.venv\Scripts\activate.bat"
	@echo "  macOS/Linux: source .venv/bin/activate"

# -----------------------------
# Install dependencies
# -----------------------------

install:
	.venv\Scripts\python.exe -m pip install --upgrade pip
	.venv\Scripts\pip install -r requirements.txt

# -----------------------------
# Testing
# -----------------------------

test:
	.venv\Scripts\pytest -v -m "not slow"

# 80%+ coverage is a floor enforced in CI, not just a locally-run number
# to ignore (docs/requirements/09-testing-strategy.md §Target: 80%+
# coverage). `make test` alone (above) still runs fast during local
# iteration without pytest-cov overhead.
coverage:
	.venv\Scripts\pytest -v -m "not slow" --cov=pipeline --cov=backend --cov-report=term-missing --cov-fail-under=80

# -----------------------------
# Linting & formatting
# -----------------------------

lint:
	.venv\Scripts\ruff check .
	.venv\Scripts\black --check .

format:
	.venv\Scripts\black .
	.venv\Scripts\ruff check . --fix

typecheck:
	.venv\Scripts\mypy .

# Run all quality checks (lint + types + tests + coverage gate)
check: lint typecheck coverage

# -----------------------------
# Run the tool
# -----------------------------

run-cli:
	.venv\Scripts\python main.py

run-gui:
	.venv\Scripts\python launcher.py

all: check
