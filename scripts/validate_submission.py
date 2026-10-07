"""Validate submission files for the hidden-50 questions."""

import json
import sys
from pathlib import Path

# Ensure utf-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBMISSION_DIR = PROJECT_ROOT / "submission"
HIDDEN_FILE = PROJECT_ROOT / "Dataset" / "questions" / "eval_hidden.jsonl"

REQUIRED_FIELDS = {"question_id", "answer", "tokens", "trace", "citations"}
TOKEN_FIELDS = {"context_tokens", "llm_input_tokens", "llm_output_tokens", "total_tokens"}


def main() -> int:
    # Load hidden question IDs
    hidden_ids = set()
    with open(HIDDEN_FILE) as f:
        for line in f:
            hidden_ids.add(json.loads(line.strip())["qid"])

    assert len(hidden_ids) == 50, f"Expected 50 hidden questions, got {len(hidden_ids)}"

    errors: list[str] = []
    pipelines_found: list[str] = []

    for pipeline in ["rag", "graphrag", "agentic"]:
        path = SUBMISSION_DIR / f"hidden50_{pipeline}.jsonl"
        if not path.exists():
            errors.append(f"Missing: {path}")
            continue

        pipelines_found.append(pipeline)
        seen_ids: set[str] = set()

        with open(path) as f:
            for line_no, line in enumerate(f, 1):
                try:
                    obj = json.loads(line.strip())
                except json.JSONDecodeError:
                    errors.append(f"{path}:{line_no} — invalid JSON")
                    continue

                # Check required fields
                for field in REQUIRED_FIELDS:
                    if field not in obj:
                        errors.append(f"{path}:{line_no} — missing field '{field}'")

                qid = obj.get("question_id", "")
                if qid in seen_ids:
                    errors.append(f"{path}:{line_no} — duplicate question_id '{qid}'")
                seen_ids.add(qid)

                # Check answer is non-empty (unless error)
                if not obj.get("answer", "").strip() and not obj.get("error"):
                    errors.append(f"{path}:{line_no} — empty answer without error flag")

                # Check token invariants
                tokens = obj.get("tokens", {})
                if tokens:
                    for tf in TOKEN_FIELDS:
                        if tf not in tokens:
                            errors.append(f"{path}:{line_no} — missing token field '{tf}'")
                    total = tokens.get("total_tokens", 0)
                    expected = tokens.get("llm_input_tokens", 0) + tokens.get("llm_output_tokens", 0)
                    if total != expected:
                        errors.append(f"{path}:{line_no} — token invariant: {total} != {expected}")

                # Check no ground truth leaked
                for forbidden in ["gold_doc_ids", "answer_verified", "ground_truth"]:
                    if forbidden in obj:
                        errors.append(f"{path}:{line_no} — forbidden field '{forbidden}' in submission")

        # Check all 50 questions present
        if seen_ids != hidden_ids:
            missing = hidden_ids - seen_ids
            extra = seen_ids - hidden_ids
            if missing:
                errors.append(f"{path} — missing question IDs: {missing}")
            if extra:
                errors.append(f"{path} — extra question IDs not in hidden set: {extra}")

    if errors:
        print(f"❌ VALIDATION FAILED ({len(errors)} errors):")
        for e in errors:
            print(f"  {e}")
        return 1
    else:
        print(f"✅ Submission valid. Pipelines: {pipelines_found}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
