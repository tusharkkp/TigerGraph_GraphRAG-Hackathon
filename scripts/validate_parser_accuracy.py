"""
Validate StructuredInfoboxParser fields against gold answers in eval_public.jsonl.

Computes exact factual accuracy (not merely coverage) on lookup and aggregation questions.
Writes audit results to reports/parser_accuracy.md.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from src.ingestion.structured_parser import StructuredInfoboxParser
from src.utils.normalization import build_match_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CORPUS_PATH = Path("Dataset/corpus/corpus.jsonl")
QUESTIONS_PATH = Path("Dataset/questions/eval_public.jsonl")
REPORTS_DIR = Path("reports")


def validate_parser_accuracy() -> dict[str, Any]:
    logger.info("Loading corpus...")
    corpus = {}
    with open(CORPUS_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            corpus[d["doc_id"]] = d

    logger.info("Parsing all corpus documents with StructuredInfoboxParser...")
    parsed_docs: dict[str, Any] = {}
    infobox_count = 0
    for doc_id, doc in corpus.items():
        parsed = StructuredInfoboxParser.parse_document(doc)
        if parsed:
            parsed_docs[doc_id] = parsed
            infobox_count += 1

    logger.info("Parsed %d/%d documents with infoboxes.", infobox_count, len(corpus))

    logger.info("Auditing lookup and aggregation questions against parsed structured fields...")
    total_eval = 0
    exact_matches = 0
    field_counts = defaultdict(int)
    field_matches = defaultdict(int)
    sample_evals = []

    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            qtype = q.get("qtype")
            qid = q.get("qid")
            gold_answers = q.get("answer", [])
            gold_docs = q.get("gold_doc_ids", [])

            if not gold_answers or not gold_docs:
                continue

            # Check if this question is asking about a structured field from infobox
            q_text = q.get("question", "").lower()
            matched_field = None
            extracted_val = None

            for g_id in gold_docs:
                parsed = parsed_docs.get(g_id)
                if not parsed:
                    continue

                if "how many nations" in q_text:
                    matched_field = "nations"
                    extracted_val = str(parsed.nations) if parsed.nations is not None else None
                elif "how many competitors" in q_text or "how many athletes" in q_text:
                    matched_field = "competitors"
                    extracted_val = str(parsed.competitors) if parsed.competitors is not None else None
                elif "who won the gold medal" in q_text or "who won gold" in q_text or "gold medalist" in q_text:
                    matched_field = "gold_medalist"
                    gold_medalists = [m.athlete_name for m in parsed.medals if m.medal == "Gold"]
                    extracted_val = gold_medalists[0] if gold_medalists else None
                elif "venue" in q_text or "held at" in q_text:
                    matched_field = "venue"
                    extracted_val = parsed.venue if parsed.venue else None

                if matched_field and extracted_val:
                    break

            if matched_field:
                total_eval += 1
                field_counts[matched_field] += 1

                # Normalize and compare
                ext_key = build_match_key(str(extracted_val))
                gold_keys = [build_match_key(str(a)) for a in gold_answers]

                is_match = ext_key in gold_keys or any(ext_key == gk for gk in gold_keys)
                if is_match:
                    exact_matches += 1
                    field_matches[matched_field] += 1

                if len(sample_evals) < 25:
                    sample_evals.append({
                        "qid": qid,
                        "question": q.get("question"),
                        "field": matched_field,
                        "extracted": extracted_val,
                        "gold": gold_answers,
                        "match": is_match,
                    })

    overall_accuracy = (exact_matches / total_eval * 100) if total_eval > 0 else 0.0

    logger.info("Validation complete! Tested %d questions.", total_eval)
    logger.info("Overall Accuracy: %.2f%% (%d/%d)", overall_accuracy, exact_matches, total_eval)

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / "parser_accuracy.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Structured Parser Factual Accuracy Report\n\n")
        f.write(f"**Overall Factual Accuracy:** {overall_accuracy:.1f}% ({exact_matches}/{total_eval})\n\n")
        f.write("## Accuracy by Field Type\n")
        f.write("| Field | Evaluated Questions | Exact Matches | Accuracy % |\n")
        f.write("|---|---|---|---|\n")
        for fld, cnt in sorted(field_counts.items()):
            m_cnt = field_matches[fld]
            pct = (m_cnt / cnt * 100) if cnt > 0 else 0
            f.write(f"| `{fld}` | {cnt} | {m_cnt} | **{pct:.1f}%** |\n")

        f.write("\n## Sample Question Audits\n")
        f.write("| QID | Field | Extracted Value | Gold Answer | Result |\n")
        f.write("|---|---|---|---|---|\n")
        for s in sample_evals:
            res_str = "PASS" if s["match"] else "FAIL"
            f.write(f"| {s['qid']} | `{s['field']}` | {s['extracted']} | {s['gold']} | {res_str} |\n")

    logger.info("Saved report to %s", report_file)
    return {
        "total_eval": total_eval,
        "exact_matches": exact_matches,
        "accuracy": overall_accuracy,
        "field_counts": dict(field_counts),
        "field_matches": dict(field_matches),
    }


if __name__ == "__main__":
    validate_parser_accuracy()
