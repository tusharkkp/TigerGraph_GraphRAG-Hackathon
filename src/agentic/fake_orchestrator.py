"""
FakeOrchestrator: Deterministic, quota-free agentic orchestrator for behavior testing and baseline validation.

Executes the Phase 3 Agentic GraphRAG control flow using deterministic sub-agents
and simulated or mocked tool executions, producing 100% contract-compliant PipelineResults.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from src.agentic.entity_linker import EntityLinker
from src.agentic.evaluator import EvidenceEvaluator
from src.contracts import Citation, PipelineResult, TokenUsage, TraceStep


class FakeOrchestrator:
    """Mockable orchestrator executing the agentic state machine with zero external LLM calls."""

    def __init__(
        self,
        tool_dispatch_override: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        max_steps: int = 3,
        token_cap: int = 4000,
    ) -> None:
        self.tool_dispatch_override = tool_dispatch_override
        self.max_steps = max_steps
        self.token_cap = token_cap

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch tool call to override or deterministic simulator."""
        if self.tool_dispatch_override:
            return self.tool_dispatch_override(tool_name, args)

        # Default simulator behavior based on tool name
        if tool_name == "Resolve_Entity":
            return {
                "matches": [{"id": "event_123", "name": args.get("query", "")}],
                "source_doc_ids": ["Q123"],
            }
        elif tool_name == "Find_Events":
            return {
                "total_count": 4,
                "events": [{"event_id": "event_123", "name": "Event 1"}],
                "source_doc_ids": ["Q123", "Q456"],
            }
        elif tool_name == "Event_Details":
            return {
                "event_id": args.get("event_id", ""),
                "medalists": [{"name": "Sample Athlete", "noc": "USA", "medal": "Gold"}],
                "source_doc_ids": ["Q123"],
            }
        elif tool_name == "Navigate_Edition":
            return {
                "target_event_id": "event_prev_456",
                "medalists": [{"name": "Prior Winner", "medal": "Gold"}],
                "source_doc_ids": ["Q789"],
            }
        return {"rows": [], "source_doc_ids": []}

    def run(
        self,
        question: str,
        question_id: str = "mock-001",
        plan_steps: list[tuple[str, str, dict[str, Any]]] | None = None,
    ) -> PipelineResult:
        """
        Execute the agentic flow on a question.
        
        Args:
            question: Natural language question.
            question_id: Identifier for the question.
            plan_steps: Optional explicit list of (agent_name, tool_name, args) to execute.
        """
        start_time = time.perf_counter()
        evaluator = EvidenceEvaluator(max_steps=self.max_steps, token_cap=self.token_cap)
        trace: list[TraceStep] = []
        citations: list[Citation] = []
        all_retrieved_chunks: list[str] = []

        total_tokens_in = 0
        total_tokens_out = 0
        stop_reason = None
        strategy_changed = False

        # Step 0: Deterministic Entity Linking
        linked = EntityLinker.link_question(question)

        # If no explicit plan provided, build default deterministic plan from linked entities
        if not plan_steps:
            if "how many" in question.lower() or linked.min_competitors:
                plan_steps = [
                    (
                        "GraphTraversal",
                        "Find_Events",
                        {
                            "sport_name": linked.sport or "",
                            "year_val": linked.year or 0,
                            "min_comp": linked.min_competitors or 0,
                        },
                    )
                ]
            else:
                plan_steps = [
                    (
                        "EntityLinker",
                        "Resolve_Entity",
                        {"query": linked.sport or question[:30], "entity_type": "event"},
                    ),
                    (
                        "GraphTraversal",
                        "Event_Details",
                        {"event_id": "event_123"},
                    ),
                ]

        step_counter = 1
        for i, (agent_name, tool_name, args) in enumerate(plan_steps, start=1):
            is_last = (i == len(plan_steps))
            step_start = time.perf_counter()

            # Execute tool
            obs = self._execute_tool(tool_name, args)
            step_latency_ms = int((time.perf_counter() - step_start) * 1000)

            # Simulated token tracking per step
            t_in = 150 + len(str(args))
            t_out = 50 + len(str(obs))
            total_tokens_in += t_in
            total_tokens_out += t_out

            eval_res = evaluator.evaluate_step(
                step_num=step_counter,
                tool_name=tool_name,
                tool_args=args,
                observation=obs,
                tokens_so_far=total_tokens_in + total_tokens_out,
                is_final_step_planned=is_last,
            )

            # Collect citations
            for doc_id in obs.get("source_doc_ids", []):
                chunk_id = f"{doc_id}_c001"
                citations.append(Citation(chunk_id=chunk_id, doc_id=doc_id, quote=None))
                all_retrieved_chunks.append(chunk_id)

            if eval_res.decision == "change_strategy":
                strategy_changed = True

            trace.append(
                TraceStep(
                    step=step_counter,
                    agent=agent_name,
                    tool=tool_name,
                    args=args,
                    rationale=eval_res.rationale,
                    observation_summary=f"Observation with {len(obs)} fields.",
                    new_evidence_ids=obs.get("source_doc_ids", []),
                    tokens_in=t_in,
                    tokens_out=t_out,
                    latency_ms=step_latency_ms,
                    strategy_tag="deterministic_plan",
                    decision=eval_res.decision,
                )
            )

            step_counter += 1

            if eval_res.decision == "stop":
                stop_reason = eval_res.stop_reason
                break

        # Invariant safeguard: contract mandates that the last step MUST have decision="stop"
        if trace and trace[-1].decision != "stop":
            trace[-1].decision = "stop"
            if not stop_reason:
                stop_reason = "SUFFICIENCY_REACHED"

        total_latency_ms = int((time.perf_counter() - start_time) * 1000)
        token_usage = TokenUsage(
            context_tokens=min(total_tokens_in, 200),
            llm_input_tokens=total_tokens_in,
            llm_output_tokens=total_tokens_out,
            total_tokens=total_tokens_in + total_tokens_out,
        )

        return PipelineResult(
            question_id=question_id,
            pipeline="agentic",
            answer="Deterministic Answer Generated",
            citations=citations,
            retrieved_chunk_ids=all_retrieved_chunks,
            tokens=token_usage,
            latency_ms=total_latency_ms,
            trace=trace,
            stop_reason=stop_reason or "SUFFICIENCY_REACHED",
            strategy_changed=strategy_changed,
            error=None,
        )
