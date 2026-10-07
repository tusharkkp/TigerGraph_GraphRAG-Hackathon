"""
Judge Calibration Script.

Evaluates the two-stage judge on 20 controlled test pairs:
1. Exact matches (should PASS on Stage 1, 0 LLM calls)
2. Normalization / diacritics variants (should PASS on Stage 1)
3. Paraphrased / full-sentence answers (should FAIL Stage 1, PASS Stage 2)
4. Incorrect / hallucinated answers (should FAIL Stage 1, FAIL Stage 2)

Writes results and metrics to reports/judge_calibration.md.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.config import PROJECT_ROOT, REPORTS_DIR
from src.eval.judge import TwoStageJudge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CALIBRATION_CASES = [
    # Category 1: Exact matches (Stage 1 should PASS)
    {
        "qid": "cal-01",
        "question": "Who won the men's 20 km walk at the 2012 Summer Olympics?",
        "gold": ["Chen Ding"],
        "candidate": "Chen Ding",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-02",
        "question": "How many nations competed in the event?",
        "gold": ["26"],
        "candidate": "26",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-03",
        "question": "Who won gold in women's 57 kg judo at the 2016 Summer Olympics?",
        "gold": ["Rafaela Silva"],
        "candidate": "Rafaela Silva",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-04",
        "question": "Who won the gold medal in men's pole vault in 2012?",
        "gold": ["Renaud Lavillenie"],
        "candidate": "Renaud Lavillenie",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-05",
        "question": "How many competitors participated?",
        "gold": ["34"],
        "candidate": "34",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    # Category 2: Diacritics / Transliteration (Stage 1 should PASS)
    {
        "qid": "cal-06",
        "question": "Who won gold in women's 5000 metres speed skating in 2010?",
        "gold": ["Martina Sáblíková"],
        "candidate": "Martina Sablikova",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-07",
        "question": "Who won men's 60 kg weightlifting in 1988?",
        "gold": ["Naim Süleymanoğlu"],
        "candidate": "Naim Suleymanoglu",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-08",
        "question": "Who won men's cross-country cycling in 2012?",
        "gold": ["Jaroslav Kulhavý"],
        "candidate": "Jaroslav Kulhavy",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-09",
        "question": "Who won women's épée in 2016?",
        "gold": ["Emese Szász"],
        "candidate": "Emese Szasz",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-10",
        "question": "Who won men's 85 kg weightlifting in 2004?",
        "gold": ["Pyrros Dimas"],
        "candidate": "Pyrros Dimas",
        "expected_stage": "Stage 1",
        "expected_verdict": "PASS",
    },
    # Category 3: Semantic equivalence / sentence framing (Stage 1 FAILS, Stage 2 should PASS)
    {
        "qid": "cal-11",
        "question": "Who won the men's 20 km walk in 2012?",
        "gold": ["Chen Ding"],
        "candidate": "The gold medal was won by the Chinese athlete Chen Ding.",
        "expected_stage": "Stage 2",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-12",
        "question": "How many nations participated in the event?",
        "gold": ["26"],
        "candidate": "A total of 26 different countries participated in the competition.",
        "expected_stage": "Stage 2",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-13",
        "question": "Where was the 2000 Olympic aquatic events held?",
        "gold": ["Sydney International Aquatic Centre"],
        "candidate": "Sydney Aquatic Centre",
        "expected_stage": "Stage 2",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-14",
        "question": "Who won gold in women's singles badminton in 2016?",
        "gold": ["Carolina Marín"],
        "candidate": "Carolina Marin from Spain took the gold medal.",
        "expected_stage": "Stage 2",
        "expected_verdict": "PASS",
    },
    {
        "qid": "cal-15",
        "question": "How many athletes took part in the event?",
        "gold": ["30"],
        "candidate": "There were 30 competitors in total.",
        "expected_stage": "Stage 2",
        "expected_verdict": "PASS",
    },
    # Category 4: Incorrect / Hallucinated answers (Stage 1 FAILS, Stage 2 should FAIL)
    {
        "qid": "cal-16",
        "question": "Who won the men's 20 km walk in 2012?",
        "gold": ["Chen Ding"],
        "candidate": "Usain Bolt",
        "expected_stage": "Stage 2",
        "expected_verdict": "FAIL",
    },
    {
        "qid": "cal-17",
        "question": "How many nations participated in the event?",
        "gold": ["26"],
        "candidate": "42",
        "expected_stage": "Stage 2",
        "expected_verdict": "FAIL",
    },
    {
        "qid": "cal-18",
        "question": "Who won gold in women's 57 kg judo in 2016?",
        "gold": ["Rafaela Silva"],
        "candidate": "Dorjsürengiin Sumiya",  # Silver medalist, not gold
        "expected_stage": "Stage 2",
        "expected_verdict": "FAIL",
    },
    {
        "qid": "cal-19",
        "question": "Where was the sailing event held in 2012?",
        "gold": ["Weymouth and Portland National Sailing Academy"],
        "candidate": "Wembley Stadium",
        "expected_stage": "Stage 2",
        "expected_verdict": "FAIL",
    },
    {
        "qid": "cal-20",
        "question": "How many competitors participated?",
        "gold": ["34"],
        "candidate": "12",
        "expected_stage": "Stage 2",
        "expected_verdict": "FAIL",
    },
]


def run_calibration() -> None:
    judge = TwoStageJudge()
    logger.info("Running judge calibration across %d test cases...", len(CALIBRATION_CASES))

    results = []
    correct_evaluations = 0

    for case in CALIBRATION_CASES:
        res = judge.evaluate(
            question_id=case["qid"],
            question=case["question"],
            gold_answers=case["gold"],
            candidate_answer=case["candidate"],
            pipeline="CALIBRATION",
        )

        stage_used = "Stage 1" if "Stage 1" in res.reason else "Stage 2"
        if stage_used == "Stage 2":
            time.sleep(1.0)
        is_verdict_correct = (res.verdict == case["expected_verdict"])
        is_stage_correct = (stage_used == case["expected_stage"])

        if is_verdict_correct and is_stage_correct:
            correct_evaluations += 1

        results.append({
            "qid": case["qid"],
            "expected_verdict": case["expected_verdict"],
            "actual_verdict": res.verdict,
            "expected_stage": case["expected_stage"],
            "actual_stage": stage_used,
            "reason": res.reason,
            "match": is_verdict_correct and is_stage_correct,
        })
        logger.info(
            "[%s] Expected: %s (%s) | Got: %s (%s) | Reason: %s",
            case["qid"],
            case["expected_verdict"],
            case["expected_stage"],
            res.verdict,
            stage_used,
            res.reason[:60],
        )

    accuracy = (correct_evaluations / len(CALIBRATION_CASES)) * 100
    logger.info("Calibration Complete! Calibration Accuracy: %.1f%% (%d/%d)", accuracy, correct_evaluations, len(CALIBRATION_CASES))

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / "judge_calibration.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Two-Stage Judge Calibration Report\n\n")
        f.write(f"**Overall Calibration Accuracy:** {accuracy:.1f}% ({correct_evaluations}/{len(CALIBRATION_CASES)})\n\n")
        f.write("## Calibration Test Cases\n\n")
        f.write("| QID | Expected Stage | Actual Stage | Expected Verdict | Actual Verdict | Reason | Status |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in results:
            stat_icon = "PASS" if r["match"] else "FAIL"
            f.write(f"| {r['qid']} | {r['expected_stage']} | {r['actual_stage']} | {r['expected_verdict']} | {r['actual_verdict']} | `{r['reason'][:80]}` | **{stat_icon}** |\n")

    logger.info("Saved calibration report to %s", report_file)


if __name__ == "__main__":
    run_calibration()
