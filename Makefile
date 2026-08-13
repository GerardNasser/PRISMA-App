.PHONY: help run test lint fields-validate build clean

help:
	@echo "Targets:"
	@echo "  run              start the desktop app from source"
	@echo "  test             run the test suite"
	@echo "  lint             ruff check on the engine, GUI, and tests"
	@echo "  fields-validate  validate all field config YAMLs against the schema"
	@echo "  build            PyInstaller bundle (.app/.dmg on macOS, .exe on Windows)"
	@echo "  clean            remove caches"

run:
	python3 app.py

test:
	python3 -m pytest tests/ -q

lint:
	python3 -m ruff check prismapi gui tests app.py build.py

fields-validate:
	python3 -m prismapi.fields.validate

build:
	python3 build.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
