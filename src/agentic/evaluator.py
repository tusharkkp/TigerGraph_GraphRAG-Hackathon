"""
EvidenceEvaluator: Deterministic verification and stopping evaluation (0 LLM calls).

Evaluates whether retrieved graph evidence sufficiently answers question constraints,
detects loops, and enforces budget guardrails.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EvaluationDecision:
    """Evaluation result for an agent execution step."""

    def __init__(
        self,
        decision: str,  # "continue", "stop", "change_strategy"
        stop_reason: str | None = None,
        rationale: str = "",
    ) -> None:
        self.decision = decision
        self.stop_reason = stop_reason
        self.rationale = rationale

    def __repr__(self) -> str:
        return f"EvaluationDecision(decision={self.decision}, stop_reason={self.stop_reason}, rationale='{self.rationale}')"


class EvidenceEvaluator:
    """Deterministic evidence evaluator with zero LLM overhead."""

    def __init__(
        self,
        max_steps: int = 3,
        token_cap: int = 4000,
    ) -> None:
        self.max_steps = max_steps
        self.token_cap = token_cap
        self.seen_calls: set[tuple[str, str]] = set()
        self.accumulated_doc_ids: set[str] = set()

    def evaluate_step(
        self,
        step_num: int,
        tool_name: str,
        tool_args: dict[str, Any],
        observation: dict[str, Any],
        tokens_so_far: int = 0,
        is_final_step_planned: bool = False,
    ) -> EvaluationDecision:
        """
        Evaluate step observation against deterministic invariants.
        """
        # 1. Budget: Token Cap
        if tokens_so_far >= self.token_cap:
            return EvaluationDecision(
                decision="stop",
                stop_reason="BUDGET_TOKEN_CAP",
                rationale=f"Token consumption {tokens_so_far} exceeded cap {self.token_cap}.",
            )

        # 2. Budget: Max Steps
        if step_num >= self.max_steps:
            return EvaluationDecision(
                decision="stop",
                stop_reason="BUDGET_MAX_STEPS",
                rationale=f"Step {step_num} reached maximum step budget {self.max_steps}.",
            )

        # 3. Guardrail: Loop Detection (identical tool + args)
        call_signature = (tool_name, str(sorted(tool_args.items())))
        if call_signature in self.seen_calls:
            return EvaluationDecision(
                decision="stop",
                stop_reason="LOOP_DETECTED",
                rationale=f"Loop detected: tool {tool_name} was already invoked with args {tool_args}.",
            )
        self.seen_calls.add(call_signature)

        # 4. Guardrail: Tool Error / Timeout Resilience
        if observation.get("error"):
            return EvaluationDecision(
                decision="change_strategy",
                stop_reason=None,
                rationale=f"Tool {tool_name} reported error: {observation['error']}. Falling back.",
            )

        # 5. Extract citation doc IDs
        new_doc_ids = set(observation.get("source_doc_ids", []))
        has_new_evidence = bool(new_doc_ids - self.accumulated_doc_ids)
        self.accumulated_doc_ids.update(new_doc_ids)

        # 6. Extract observations
        rows = observation.get("rows") or observation.get("events") or observation.get("medalists")
        total_count = observation.get("total_count")

        # Guardrail: No New Evidence
        if step_num > 1 and not has_new_evidence and not rows and total_count is None:
            return EvaluationDecision(
                decision="stop",
                stop_reason="NO_NEW_EVIDENCE",
                rationale="Tool returned no new source documents or evidence.",
            )

        # 7. Sufficiency Check
        if total_count is not None and total_count >= 0:
            return EvaluationDecision(
                decision="stop",
                stop_reason="SUFFICIENCY_REACHED",
                rationale=f"Definitive aggregation count {total_count} obtained.",
            )

        if rows and len(rows) > 0:
            return EvaluationDecision(
                decision="stop",
                stop_reason="SUFFICIENCY_REACHED",
                rationale=f"Retrieved {len(rows)} matching entity rows.",
            )

        if is_final_step_planned:
            return EvaluationDecision(
                decision="stop",
                stop_reason="SUFFICIENCY_REACHED",
                rationale="Planned execution reached sufficiency.",
            )

        return EvaluationDecision(
            decision="continue",
            stop_reason=None,
            rationale="Evidence incomplete; proceeding to next step.",
        )
