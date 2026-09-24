PYTHON  := python3
MAIN    := main.py
MAP     ?= maps/easy/01_linear_path.txt

.PHONY: install run debug clean lint lint-strict test bench help

help:
	@echo "Fly-in - available targets:"
	@echo "  install      Install project dependencies"
	@echo "  run          Run the simulation (MAP=<path> to choose a map)"
	@echo "  debug        Run the simulation under pdb"
	@echo "  clean        Remove caches and Python artifacts"
	@echo "  lint         Run flake8 and mypy"
	@echo "  lint-strict  Run flake8 and mypy --strict"
	@echo "  test         Run the unit test suite"
	@echo "  bench        Run every provided map and report turn counts"

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) $(MAIN) $(MAP)

debug:
	$(PYTHON) -m pdb $(MAIN) $(MAP)

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -rf .mypy_cache .pytest_cache .ruff_cache

lint:
	flake8 .
	mypy . --warn-return-any --warn-unused-ignores \
		--ignore-missing-imports --disallow-untyped-defs \
		--check-untyped-defs

lint-strict:
	flake8 .
	mypy . --strict

test:
	$(PYTHON) -m pytest -q

bench:
	@for map in maps/easy/*.txt maps/medium/*.txt \
		maps/hard/*.txt maps/challenger/*.txt; do \
		printf '%-40s ' "$$map"; \
		$(PYTHON) $(MAIN) "$$map" --quiet --turns-only || echo "FAILED"; \
	done
