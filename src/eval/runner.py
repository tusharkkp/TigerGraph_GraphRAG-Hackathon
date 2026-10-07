"""
Benchmark Evaluation Runner for Agentic GraphRAG.

Evaluates P1 (Vector RAG), P2 (GraphRAG), and P3 (Agentic GraphRAG) across:
- splits: dev (60), val (20), test (20), all100 (100), hidden50 (50)
- metrics: Accuracy, Recall@k, Precision@k, MRR, Token Usage, Latency
- supports: --pre-check, --resume, and submission file generation
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, REPORTS_DIR, get_embedding_config
from src.contracts import JudgeResult, PipelineResult, Question
from src.eval.judge import TwoStageJudge
from src.eval.retrieval_metrics import evaluate_retrieval
from src.pipelines.p1_vector_rag import VectorRAGPipeline
from src.pipelines.p2_graphrag import GraphRAGPipeline
from src.pipelines.p3_agentic import AgenticGraphRAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SPLITS_FILE = PROJECT_ROOT / "data" / "splits.json"
PUBLIC_QUESTIONS_FILE = PROJECT_ROOT / "Dataset" / "questions" / "eval_public.jsonl"
HIDDEN_QUESTIONS_FILE = PROJECT_ROOT / "Dataset" / "questions" / "eval_hidden.jsonl"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


class BenchmarkRunner:
    """Orchestrates end-to-end evaluation runs across pipelines and splits."""

    def __init__(self, judge: TwoStageJudge | None = None) -> None:
        self.judge = judge or TwoStageJudge()
        self.p1 = VectorRAGPipeline()
        self.p2 = GraphRAGPipeline()
        self.p3 = AgenticGraphRAGPipeline()

    def load_questions(self, split: str) -> list[Question]:
        """Load questions for the requested split."""
        if split == "hidden50":
            if not HIDDEN_QUESTIONS_FILE.exists():
                raise FileNotFoundError(f"Hidden questions file not found: {HIDDEN_QUESTIONS_FILE}")
            questions = []
            with open(HIDDEN_QUESTIONS_FILE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        questions.append(Question.model_validate_json(line))
            return questions

        with open(SPLITS_FILE, encoding="utf-8") as f:
            splits_data = json.load(f)["splits"]

        if split == "all100":
            target_qids = set(splits_data["dev"] + splits_data["val"] + splits_data["test"])
        elif split in splits_data:
            target_qids = set(splits_data[split])
        else:
            raise ValueError(f"Unknown split: {split}. Expected one of: dev, val, test, all100, hidden50")

        questions_by_id = {}
        with open(PUBLIC_QUESTIONS_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    q = Question.model_validate_json(line)
                    if q.qid in target_qids:
                        questions_by_id[q.qid] = q

        # Preserve split ordering
        ordered_qids = [qid for qid in (splits_data.get(split) or target_qids) if qid in questions_by_id]
        return [questions_by_id[qid] for qid in ordered_qids]

    def pre_check(self, pipeline_name: str, split: str, count: int) -> None:
        """Estimate execution time, token budget, and quota requirements."""
        print("\n========================================================")
        print(f"PRE-CHECK ESTIMATION: Pipeline={pipeline_name.upper()} | Split={split} ({count} questions)")
        print("========================================================")

        # Realistic estimates from calibration and pilot
        time_per_q = 3.5 if pipeline_name == "p1" else 4.5
        total_time_min = round((count * time_per_q) / 60, 1)

        input_toks_per_q = 1500 if pipeline_name == "p1" else 2200
        output_toks_per_q = 100
        total_tokens = count * (input_toks_per_q + output_toks_per_q)

        judge_calls = 0 if split == "hidden50" else int(count * 0.15)  # Stage 1 resolves ~85%

        print(f"- Estimated Duration: ~{total_time_min} minutes (~{time_per_q}s per question)")
        print(f"- Estimated Input Tokens: ~{count * input_toks_per_q:,}")
        print(f"- Estimated Output Tokens: ~{count * output_toks_per_q:,}")
        print(f"- Estimated Total LLM Tokens: ~{total_tokens:,}")
        print(f"- Estimated Stage 2 LLM Judge Calls: ~{judge_calls} (Stage 1 resolves ~85% with 0 tokens)")
        print(f"- Rate Limiting: 1.0s delay between calls ensures quota safety")
        print("========================================================\n")

    def run_benchmark(
        self,
        pipeline_name: str,
        split: str,
        limit: int | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        """Execute benchmark for a pipeline across a split."""
        questions = self.load_questions(split)
        if limit:
            questions = questions[:limit]

        if pipeline_name == "p1":
            pipeline_inst = self.p1
            pipe_key = "rag"
        elif pipeline_name == "p2":
            pipeline_inst = self.p2
            pipe_key = "graphrag"
        elif pipeline_name == "p3":
            pipeline_inst = self.p3
            pipe_key = "agentic"
        else:
            raise ValueError(f"Unknown pipeline: {pipeline_name}")

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint_file = PROCESSED_DIR / f"eval_{pipeline_name}_{split}.jsonl"

        # Check existing results for resumption
        completed_results: dict[str, dict[str, Any]] = {}
        if resume and checkpoint_file.exists():
            with open(checkpoint_file, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        completed_results[item["question_id"]] = item
            logger.info("Resuming %s (%s): %d already completed.", pipeline_name, split, len(completed_results))

        is_hidden = (split == "hidden50")
        submission_records = []

        total_questions = len(questions)
        logger.info("Starting benchmark: %s on %s (%d questions)", pipeline_name.upper(), split, total_questions)

        for idx, q in enumerate(questions, start=1):
            if q.qid in completed_results:
                continue

            logger.info("[%d/%d] Evaluating %s (%s): %s", idx, total_questions, q.qid, q.qtype, q.question[:70])

            # 1. Run pipeline
            res: PipelineResult = pipeline_inst.run(q, top_k=5)

            # 2. Evaluate if not hidden
            judge_res: JudgeResult | None = None
            retrieval_eval: dict[str, float] = {}

            if not is_hidden and q.answer:
                judge_res = self.judge.evaluate(
                    question_id=q.qid,
                    question=q.question,
                    gold_answers=q.answer,
                    candidate_answer=res.answer,
                    pipeline=pipe_key,
                )
                if q.gold_doc_ids:
                    retrieval_eval = evaluate_retrieval(res.retrieved_chunk_ids, q.gold_doc_ids)

            record = {
                "question_id": q.qid,
                "qtype": q.qtype,
                "pipeline": pipe_key,
                "answer": res.answer,
                "gold_answer": q.answer if not is_hidden else None,
                "verdict": judge_res.verdict if judge_res else None,
                "completeness": judge_res.completeness if judge_res else None,
                "judge_reason": judge_res.reason if judge_res else None,
                "retrieved_chunk_ids": res.retrieved_chunk_ids,
                "gold_doc_ids": q.gold_doc_ids if not is_hidden else None,
                "retrieval_metrics": retrieval_eval,
                "tokens": res.tokens.model_dump(),
                "latency_ms": res.latency_ms,
                "embedding_model": get_embedding_config().get("model", "unknown"),
            }

            # Append to checkpoint file
            with open(checkpoint_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            completed_results[q.qid] = record

            if is_hidden:
                submission_records.append({
                    "qid": q.qid,
                    "question_id": q.qid,
                    "question": q.question,
                    "answer": res.answer,
                    "tokens": res.tokens.model_dump(),
                    "latency_sec": round(res.latency_ms / 1000.0, 3),
                    "trace": [t.model_dump() for t in res.trace],
                    "citations": [c.model_dump() for c in res.citations],
                })

            # Small delay to ensure rate limits are respected
            time.sleep(3.5)

        # If hidden, write submission file conforming to docs/round_1.txt
        if is_hidden:
            sub_file = REPORTS_DIR / "hidden50_submission.jsonl"
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            with open(sub_file, "w", encoding="utf-8") as f:
                for rec in submission_records:
                    f.write(json.dumps(rec) + "\n")
            logger.info("Saved complete hidden-50 submission to %s", sub_file)

        # Generate final report
        summary = self._generate_report(pipeline_name, split, list(completed_results.values()))
        return summary

    def _generate_report(self, pipeline_name: str, split: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate metrics and write markdown and JSON reports."""
        if not results:
            return {}

        total = len(results)
        is_hidden = (split == "hidden50")

        passes = sum(1 for r in results if r.get("verdict") == "PASS")
        accuracy = (passes / total * 100) if total > 0 and not is_hidden else 0.0

        stage1_matches = sum(1 for r in results if r.get("judge_reason") and "Stage 1" in r["judge_reason"])
        stage1_rate = (stage1_matches / total * 100) if total > 0 and not is_hidden else 0.0

        # Latency & tokens
        latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
        mean_lat = round(statistics.mean(latencies), 1) if latencies else 0.0

        total_tokens = sum(r["tokens"]["total_tokens"] for r in results if "tokens" in r)
        avg_tokens = round(total_tokens / total, 1) if total > 0 else 0.0

        # Retrieval metrics
        r1s = [r["retrieval_metrics"].get("recall@1", 0) for r in results if r.get("retrieval_metrics")]
        r5s = [r["retrieval_metrics"].get("recall@5", 0) for r in results if r.get("retrieval_metrics")]
        mrrs = [r["retrieval_metrics"].get("mrr", 0) for r in results if r.get("retrieval_metrics")]

        mean_r1 = round(statistics.mean(r1s) * 100, 1) if r1s else 0.0
        mean_r5 = round(statistics.mean(r5s) * 100, 1) if r5s else 0.0
        mean_mrr = round(statistics.mean(mrrs), 3) if mrrs else 0.0

        # Group by qtype
        by_qtype: dict[str, dict[str, Any]] = {}
        for r in results:
            qt = r.get("qtype", "unknown")
            if qt not in by_qtype:
                by_qtype[qt] = {"total": 0, "pass": 0}
            by_qtype[qt]["total"] += 1
            if r.get("verdict") == "PASS":
                by_qtype[qt]["pass"] += 1

        emb_model = get_embedding_config().get("model", "unknown")
        summary = {
            "pipeline": pipeline_name,
            "split": split,
            "embedding_model": emb_model,
            "total_questions": total,
            "accuracy": accuracy,
            "stage1_match_rate": stage1_rate,
            "mean_latency_ms": mean_lat,
            "total_tokens": total_tokens,
            "avg_tokens_per_q": avg_tokens,
            "recall@1": mean_r1,
            "recall@5": mean_r5,
            "mrr": mean_mrr,
            "by_qtype": by_qtype,
        }

        # Save JSON report
        report_json = REPORTS_DIR / f"benchmark_{pipeline_name}_{split}.json"
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Save Markdown report
        report_md = REPORTS_DIR / f"benchmark_{pipeline_name}_{split}.md"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with open(report_md, "w", encoding="utf-8") as f:
            f.write(f"# Benchmark Report: {pipeline_name.upper()} ({split})\n\n")
            f.write(f"**Generated:** {now}\n")
            f.write(f"**Embedding Model:** `{emb_model}`\n\n")
            f.write("## Overall Performance\n\n")
            f.write(f"- **Total Questions:** {total}\n")
            if not is_hidden:
                f.write(f"- **Accuracy (PASS Rate):** {accuracy:.1f}%\n")
                f.write(f"- **Stage 1 Match Rate:** {stage1_rate:.1f}% (evaluated without LLM judge)\n")
                f.write(f"- **Recall@1:** {mean_r1:.1f}%\n")
                f.write(f"- **Recall@5:** {mean_r5:.1f}%\n")
                f.write(f"- **MRR:** {mean_mrr}\n")
            f.write(f"- **Mean Latency:** {mean_lat:.0f} ms\n")
            f.write(f"- **Avg Tokens / Question:** {avg_tokens:.0f}\n\n")

            if not is_hidden:
                f.write("## Breakdown by Question Type\n\n")
                f.write("| Question Type | Total | Passes | Accuracy % |\n")
                f.write("|---|---|---|---|\n")
                for qt, d in sorted(by_qtype.items()):
                    pct = (d["pass"] / d["total"] * 100) if d["total"] > 0 else 0
                    f.write(f"| `{qt}` | {d['total']} | {d['pass']} | **{pct:.1f}%** |\n")

        logger.info("Saved benchmark report to %s and %s", report_json, report_md)
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic GraphRAG Benchmark Runner")
    parser.add_argument("--pipeline", choices=["p1", "p2", "p3", "all"], default="p1", help="Pipeline to evaluate")
    parser.add_argument("--split", choices=["dev", "val", "test", "all100", "hidden50"], default="val", help="Dataset split")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions")
    parser.add_argument("--pre-check", action="store_true", help="Print pre-check cost/time estimation and exit")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume from existing checkpoint")
    args = parser.parse_args()

    runner = BenchmarkRunner()

    pipelines_to_run = ["p1", "p2", "p3"] if args.pipeline == "all" else [args.pipeline]

    questions = runner.load_questions(args.split)
    count = min(len(questions), args.limit) if args.limit else len(questions)

    if args.pre_check:
        for p in pipelines_to_run:
            runner.pre_check(p, args.split, count)
        return

    for p in pipelines_to_run:
        runner.run_benchmark(
            pipeline_name=p,
            split=args.split,
            limit=args.limit,
            resume=not args.no_resume,
        )


if __name__ == "__main__":
    main()
