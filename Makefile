PYTHON ?= python3

.PHONY: all notebook check reproduce

all:
	$(PYTHON) scripts/run_pipeline.py
	$(PYTHON) scripts/create_notebook.py

notebook:
	$(PYTHON) -m jupyter nbconvert --execute --to notebook --inplace notebooks/carsharing_retention_case.ipynb --ExecutePreprocessor.timeout=180

check:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .
	$(PYTHON) -m pytest -q

reproduce: all notebook check
