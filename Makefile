PYTHON  := python3
VENV    := venv
VPYTHON := $(VENV)/bin/python
STAMP   := $(VENV)/.installed
MAIN    := main.py
MAP     ?= maps/easy/01_linear_path.txt

.PHONY: install run visual debug clean lint lint-strict test bench help

help:
	@echo "Fly-in - available targets:"
	@echo "  install      Create the virtualenv and install the toolchain"
	@echo "  run          Run the simulation (MAP=<path> to choose a map)"
	@echo "  visual       Run the simulation with the coloured grid view"
	@echo "  debug        Run the simulation under pdb"
	@echo "  clean        Remove caches, Python artifacts and the venv"
	@echo "  lint         Run flake8 and mypy"
	@echo "  lint-strict  Run flake8 and mypy --strict"
	@echo "  test         Run the unit test suite"
	@echo "  bench        Run every provided map and report turn counts"

# The simulation itself only needs the standard library, so run, visual,
# debug and bench use the system interpreter and work without a venv.
# The development tools live in the venv, which lint and test create
# on demand.

install: $(STAMP)

$(STAMP): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VPYTHON) -m pip install -r requirements.txt
	touch $(STAMP)

run:
	$(PYTHON) $(MAIN) $(MAP)

visual:
	$(PYTHON) $(MAIN) $(MAP) --visual --stats

debug:
	$(PYTHON) -m pdb $(MAIN) $(MAP)

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -rf .mypy_cache .pytest_cache .ruff_cache
	rm -rf $(VENV)

lint: $(STAMP)
	$(VENV)/bin/flake8 .
	$(VENV)/bin/mypy . --warn-return-any --warn-unused-ignores \
		--ignore-missing-imports --disallow-untyped-defs \
		--check-untyped-defs

lint-strict: $(STAMP)
	$(VENV)/bin/flake8 .
	$(VENV)/bin/mypy . --strict

test: $(STAMP)
	$(VPYTHON) -m pytest -q

bench:
	@for map in maps/easy/*.txt maps/medium/*.txt \
		maps/hard/*.txt maps/challenger/*.txt; do \
		printf '%-45s ' "$$map"; \
		$(PYTHON) $(MAIN) "$$map" --quiet --turns-only || echo "FAILED"; \
	done
