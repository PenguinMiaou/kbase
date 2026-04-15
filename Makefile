.PHONY: setup lint test type-check format check build release clean

# ── Development Setup ──────────────────────────────────────
setup:
	pip install -e ".[all]" && pip install -r requirements-dev.txt
	pre-commit install

# ── Quality Gates ──────────────────────────────────────────
lint:
	ruff check kbase/ tests/

format:
	ruff format kbase/ tests/
	ruff check --fix kbase/ tests/

type-check:
	pyright kbase/

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --tb=short --cov=kbase --cov-report=term-missing

# ── Combined check (CI equivalent) ────────────────────────
check: lint test
	@echo "All checks passed."

# ── Build ──────────────────────────────────────────────────
build:
	python -m build

build-dmg:
	cd kbase-desktop && npm install && npx tauri build --target aarch64-apple-darwin

build-fat:
	cd kbase-desktop && bash build-fat.sh

# ── Release ────────────────────────────────────────────────
release:
	bash release.sh

# ── Cleanup ────────────────────────────────────────────────
clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
