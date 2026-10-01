.PHONY: setup lint test test-integration verify verify-all ingest bench app validate-submission secrets-scan

PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff

# === Setup ===
setup:
	$(PYTHON) -m pip install -e ".[dev]"

# === Static checks ===
lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) format .
	$(RUFF) check --fix .

# === Tests ===
test:
	$(PYTEST) -m "unit or contract" -v --tb=short

test-unit:
	$(PYTEST) -m unit -v --tb=short

test-contract:
	$(PYTEST) -m contract -v --tb=short

test-behavior:
	$(PYTEST) -m behavior -v --tb=short

test-integration:
	$(PYTEST) -m integration -v --tb=short

# === Verification ===
verify: lint test test-behavior

verify-all: verify test-integration
	$(PYTEST) -m regression -v --tb=short

# === Ingestion ===
ingest:
	$(PYTHON) -m src.ingestion.pipeline $(ARGS)

# === Benchmark ===
bench:
	$(PYTHON) -m src.eval.runner $(ARGS)

# === Dashboard ===
app:
	$(PYTHON) -m streamlit run src/app/dashboard.py

# === Submission ===
validate-submission:
	$(PYTHON) scripts/validate_submission.py

export-hidden:
	$(PYTHON) scripts/export_hidden.py

# === Security ===
secrets-scan:
	@echo "Scanning for secrets..."
	@$(PYTHON) -c "import scripts.secrets_scan; scripts.secrets_scan.main()"

# === Fixtures ===
record-fixtures:
	$(PYTEST) -m "unit or contract" --record-fixtures -v
