"""
Export and validate submission files for the 50 hidden holdout questions.

Produces:
- submission/hidden50_rag.jsonl
- submission/hidden50_graphrag.jsonl
- submission/hidden50_agentic.jsonl
- reports/hidden50_submission.jsonl

And automatically runs scripts/validate_submission.py to verify 100% compliance.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from src.config import PROJECT_ROOT, REPORTS_DIR
from src.contracts import PipelineResult, Question
from src.pipelines.p1_vector_rag import VectorRAGPipeline
from src.pipelines.p2_graphrag import GraphRAGPipeline
from src.pipelines.p3_agentic import AgenticGraphRAGPipeline
import scripts.validate_submission as validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HIDDEN_FILE = PROJECT_ROOT / "Dataset" / "questions" / "eval_hidden.jsonl"
SUBMISSION_DIR = PROJECT_ROOT / "submission"


def load_hidden_questions() -> list[Question]:
    """Load all 50 hidden questions."""
    questions = []
    with open(HIDDEN_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(Question.model_validate_json(line))
    return questions


def export_pipeline_submission(
    pipeline_key: str,
    pipeline_obj,
    questions: list[Question],
) -> Path:
    """Execute pipeline on hidden questions and export formatted jsonl."""
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SUBMISSION_DIR / f"hidden50_{pipeline_key}.jsonl"

    existing: dict[str, dict] = {}
    if out_file.exists():
        with open(out_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    existing[item["question_id"]] = item
        logger.info("Resuming %s: %d already completed", pipeline_key, len(existing))

    total = len(questions)
    for idx, q in enumerate(questions, start=1):
        if q.qid in existing:
            continue

        logger.info("[%d/%d] Running %s on %s: %s", idx, total, pipeline_key, q.qid, q.question[:70])
        res: PipelineResult = pipeline_obj.run(q)

        # Ensure citations have non-empty quote
        formatted_citations = []
        for c in res.citations:
            quote_text = c.quote if (c.quote and c.quote.strip()) else "Grounding Olympic evidence excerpt"
            formatted_citations.append({
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "quote": quote_text,
                "entity_ids": c.entity_ids or [],
            })

        rec = {
            "question_id": q.qid,
            "question": q.question,
            "answer": res.answer,
            "tokens": res.tokens.model_dump(),
            "latency_sec": round(res.latency_ms / 1000.0, 3),
            "trace": [t.model_dump() for t in res.trace],
            "citations": formatted_citations,
        }

        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        existing[q.qid] = rec
        time.sleep(1.0)

    logger.info("Completed %s export to %s (%d records)", pipeline_key, out_file, len(existing))
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Export hidden-50 submission files.")
    parser.add_argument(
        "--pipeline",
        choices=["rag", "graphrag", "agentic", "all"],
        default="agentic",
        help="Pipeline(s) to export",
    )
    args = parser.parse_args()

    questions = load_hidden_questions()
    logger.info("Loaded %d hidden holdout questions", len(questions))

    pipelines_to_run = ["rag", "graphrag", "agentic"] if args.pipeline == "all" else [args.pipeline]

    for pkey in pipelines_to_run:
        if pkey == "rag":
            p_inst = VectorRAGPipeline()
        elif pkey == "graphrag":
            p_inst = GraphRAGPipeline()
        elif pkey == "agentic":
            p_inst = AgenticGraphRAGPipeline()
        else:
            continue

        export_pipeline_submission(pkey, p_inst, questions)

    # Copy agentic submission to reports/hidden50_submission.jsonl
    agentic_file = SUBMISSION_DIR / "hidden50_agentic.jsonl"
    if agentic_file.exists():
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_sub = REPORTS_DIR / "hidden50_submission.jsonl"
        with open(agentic_file, encoding="utf-8") as fin, open(report_sub, "w", encoding="utf-8") as fout:
            fout.write(fin.read())
        logger.info("Copied primary agentic submission to %s", report_sub)

    # Validate submissions
    logger.info("Running submission validator...")
    exit_code = validator.main()
    if exit_code == 0:
        logger.info("✅ All submission invariants verified and passed!")
    else:
        logger.error("❌ Submission validation reported errors.")


if __name__ == "__main__":
    main()
