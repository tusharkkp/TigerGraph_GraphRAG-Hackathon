"""
Two-Stage Evaluation Judge for QA Pipelines.

Stage 1: Deterministic tight normalized equality.
- Uses build_match_key to compare candidate and gold answers.
- For list answers, tests exact set equality of normalized match keys.
- Under NO circumstances awards PASS for substring containment or partial overlap.
- Zero LLM tokens spent on exact matches.

Stage 2: LLM Judge on Mismatch.
- Evaluates candidate semantic equivalence via gemini-2.5-pro at temperature 0.0.
- Assesses completeness (0.0 to 1.0), missing facts, contradictions, and short reason (<200 chars).
- Returns structured JudgeResult.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from src.contracts import CallTag, JudgeResult
from src.llm.gateway import LLMGateway
from src.utils.normalization import build_match_key

logger = logging.getLogger(__name__)


class JudgeLLMResponse(BaseModel):
    """Schema for Stage 2 LLM evaluation."""

    verdict: Literal["PASS", "FAIL"] = Field(description="PASS if candidate matches gold reference factually; FAIL otherwise")
    completeness: float = Field(ge=0.0, le=1.0, description="Score from 0.0 to 1.0 reflecting completeness of answer")
    missing_facts: list[str] = Field(default_factory=list, description="Key factual claims missing from candidate")
    contradictions: list[str] = Field(default_factory=list, description="Direct factual contradictions in candidate")
    reason: str = Field(max_length=200, description="Concise rationale under 200 characters")


STAGE2_JUDGE_PROMPT = """You are an expert Olympic QA Evaluation Judge.
Evaluate whether the candidate answer factually and accurately matches the gold reference answer.

Question ID: {qid}
Question: {question}
Gold Reference Answer(s): {gold_answers}

Candidate Answer: {candidate_answer}
Candidate Explanation: {candidate_explanation}

Evaluation Guidelines:
1. Verdict must be "PASS" if and only if the candidate answer provides the correct factual answer matching the gold reference.
2. Minor formatting differences (e.g., "Chen Ding" vs "Chen Ding (CHN)" or "26" vs "26 nations") are acceptable as long as the core fact is identical.
3. For multi-entity answers (e.g. team members or lists), all entities must be correctly identified.
4. For counts or dates, numbers and years must be exact.
5. If the candidate contains incorrect names, wrong facts, or misses the core answer, verdict must be "FAIL".
6. Keep reason strictly under 200 characters.

Return ONLY a JSON object matching the JudgeLLMResponse schema.
"""


class TwoStageJudge:
    """Evaluates pipeline answers against gold ground-truth references."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self.gateway = gateway or LLMGateway()

    def stage1_deterministic_match(
        self,
        candidate_answer: str,
        gold_answers: Sequence[str],
    ) -> bool:
        """
        Tight deterministic equality check.
        NO substring containment or partial overlap allowed.
        """
        if not candidate_answer or not gold_answers:
            return False

        cand_key = build_match_key(candidate_answer)
        if not cand_key:
            return False

        # 1. Direct normalized scalar match against any gold answer variant
        for gold in gold_answers:
            if cand_key == build_match_key(gold):
                return True

        # 2. Set equality check for multi-entity / team answers
        # Candidate split on comma, semicolon, newline, or ' and '
        import re
        cand_raw_parts = re.split(r"[,;\n]|\s+and\s+", candidate_answer)
        cand_parts = {build_match_key(p) for p in cand_raw_parts if build_match_key(p)}

        # Gold parts: unpack comma-separated or camelCase concatenated team names
        gold_parts = set()
        for g in gold_answers:
            if "," in g or ";" in g or "\n" in g:
                for sub in re.split(r"[,;\n]", g):
                    k = build_match_key(sub)
                    if k:
                        gold_parts.add(k)
            else:
                from src.ingestion.structured_parser import split_team_medalists
                splits = split_team_medalists(g)
                if len(splits) > 1:
                    for name, _ in splits:
                        k = build_match_key(name)
                        if k:
                            gold_parts.add(k)
                else:
                    k = build_match_key(g)
                    if k:
                        gold_parts.add(k)

        if len(gold_parts) > 1 and cand_parts == gold_parts:
            return True

        return False

    def evaluate(
        self,
        question_id: str,
        question: str,
        gold_answers: Sequence[str],
        candidate_answer: str,
        candidate_explanation: str = "",
        pipeline: str = "P1",
    ) -> JudgeResult:
        """
        Evaluate a candidate answer using Stage 1 deterministic check,
        falling back to Stage 2 LLM judge only upon mismatch.
        """
        # --- Stage 1: Deterministic Check ---
        if self.stage1_deterministic_match(candidate_answer, gold_answers):
            return JudgeResult(
                question_id=question_id,
                pipeline=pipeline,
                verdict="PASS",
                completeness=1.0,
                missing_facts=[],
                contradictions=[],
                reason="Stage 1 deterministic normalized match",
            )

        # --- Stage 2: LLM Judge on Mismatch ---
        prompt = STAGE2_JUDGE_PROMPT.format(
            qid=question_id,
            question=question,
            gold_answers=list(gold_answers),
            candidate_answer=candidate_answer,
            candidate_explanation=candidate_explanation or "None provided",
        )

        try:
            res = self.gateway.generate(
                role="judge",
                prompt=prompt,
                schema=JudgeLLMResponse,
                temperature=0.0,
                max_output_tokens=512,
                tag=CallTag(question_id=question_id, pipeline=pipeline, role="judge"),
            )

            if res.parsed and isinstance(res.parsed, JudgeLLMResponse):
                parsed: JudgeLLMResponse = res.parsed
                # Enforce max 200 char limit
                reason = parsed.reason[:200]
                return JudgeResult(
                    question_id=question_id,
                    pipeline=pipeline,
                    verdict=parsed.verdict,
                    completeness=parsed.completeness,
                    missing_facts=parsed.missing_facts,
                    contradictions=parsed.contradictions,
                    reason=reason,
                )
            else:
                return JudgeResult(
                    question_id=question_id,
                    pipeline=pipeline,
                    verdict="FAIL",
                    completeness=0.0,
                    missing_facts=["Failed to parse judge output"],
                    contradictions=[],
                    reason="Stage 2 LLM judge parsing failure",
                )

        except Exception as e:
            logger.error("Stage 2 LLM judge error for %s: %s", question_id, e)
            return JudgeResult(
                question_id=question_id,
                pipeline=pipeline,
                verdict="FAIL",
                completeness=0.0,
                missing_facts=[f"Judge exception: {str(e)[:100]}"],
                contradictions=[],
                reason=f"Stage 2 exception: {str(e)[:150]}",
            )
