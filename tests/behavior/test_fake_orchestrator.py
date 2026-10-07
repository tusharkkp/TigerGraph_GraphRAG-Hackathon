"""
Unit and behavior tests for the Agentic Orchestrator stopping rules, guardrails, and contract compliance.

These tests consume ZERO external LLM quota (100% offline, deterministic).
"""

from __future__ import annotations

import pytest

from src.agentic.fake_orchestrator import FakeOrchestrator
from src.contracts import PipelineResult


def test_sufficiency_early_stop():
    """Verify single-hop lookup reaches sufficiency and terminates early in <= 2 steps."""
    orch = FakeOrchestrator(max_steps=3)
    res = orch.run(
        question="Which athlete won gold in the 2008 100m?",
        question_id="test-suff-001",
    )
    assert isinstance(res, PipelineResult)
    assert len(res.trace) <= 2
    assert res.stop_reason == "SUFFICIENCY_REACHED"
    assert res.trace[-1].decision == "stop"


def test_budget_step_enforcement():
    """Verify orchestrator clamps execution at max_steps."""
    orch = FakeOrchestrator(max_steps=2)

    # 4-step plan exceeding max_steps=2
    forced_plan = [
        ("Agent1", "ToolA", {"param": 1}),
        ("Agent2", "ToolB", {"param": 2}),
        ("Agent3", "ToolC", {"param": 3}),
        ("Agent4", "ToolD", {"param": 4}),
    ]

    res = orch.run(
        question="Find previous edition winner across 4 hops",
        question_id="test-budget-002",
        plan_steps=forced_plan,
    )
    assert len(res.trace) == 2
    assert res.stop_reason == "BUDGET_MAX_STEPS"
    assert res.trace[-1].decision == "stop"


def test_token_cap_enforcement():
    """Verify orchestrator gracefully halts when cumulative token budget is exceeded."""
    orch = FakeOrchestrator(max_steps=5, token_cap=250)

    # Each step will consume ~200+ tokens
    forced_plan = [
        ("Agent1", "ToolA", {"param": "x" * 50}),
        ("Agent2", "ToolB", {"param": "y" * 50}),
    ]

    res = orch.run(
        question="Complex multi-hop question consuming large token context",
        question_id="test-token-003",
        plan_steps=forced_plan,
    )
    assert res.stop_reason == "BUDGET_TOKEN_CAP"
    assert res.trace[-1].decision == "stop"


def test_loop_detection_break():
    """Verify duplicate tool calls with identical arguments trigger immediate loop break."""
    orch = FakeOrchestrator(max_steps=5)

    # Intentionally duplicate step 1 and step 2
    forced_plan = [
        ("Agent1", "Resolve_Entity", {"query": "Swimming"}),
        ("Agent1", "Resolve_Entity", {"query": "Swimming"}),  # duplicate
    ]

    res = orch.run(
        question="Swimming events",
        question_id="test-loop-004",
        plan_steps=forced_plan,
    )
    assert res.stop_reason == "LOOP_DETECTED"
    assert len(res.trace) == 2
    assert res.trace[-1].decision == "stop"


def test_no_new_evidence_stop():
    """Verify execution halts if consecutive steps return no new documents or evidence."""
    # Override dispatcher to return empty docs on second step
    def mock_empty_dispatch(tool_name: str, args: dict):
        if tool_name == "FirstTool":
            return {"matches": [{"id": 1}], "source_doc_ids": ["Q100"]}
        return {"rows": [], "source_doc_ids": []}

    orch = FakeOrchestrator(tool_dispatch_override=mock_empty_dispatch, max_steps=4)
    forced_plan = [
        ("Agent1", "FirstTool", {"a": 1}),
        ("Agent2", "SecondTool", {"b": 2}),
    ]

    res = orch.run(
        question="Question yielding zero new evidence on step 2",
        question_id="test-no-ev-005",
        plan_steps=forced_plan,
    )
    assert res.stop_reason == "NO_NEW_EVIDENCE"
    assert res.trace[-1].decision == "stop"


def test_tool_failure_resilience():
    """Verify simulated GSQL error does not crash the orchestrator and marks strategy change."""
    def mock_failing_dispatch(tool_name: str, args: dict):
        if tool_name == "FailingTool":
            return {"error": "Savanna connection timeout", "source_doc_ids": []}
        return {"total_count": 5, "source_doc_ids": ["Q200"]}

    orch = FakeOrchestrator(tool_dispatch_override=mock_failing_dispatch, max_steps=3)
    forced_plan = [
        ("Agent1", "FailingTool", {"x": 1}),
        ("Agent2", "FallbackTool", {"y": 2}),
    ]

    res = orch.run(
        question="Question experiencing transient tool failure",
        question_id="test-fail-006",
        plan_steps=forced_plan,
    )
    assert res.error is None
    assert res.strategy_changed is True
    assert res.trace[0].decision == "change_strategy"
    assert res.trace[-1].decision == "stop"


def test_trace_contract_schema():
    """Verify that generated PipelineResult strictly satisfies all contract schema constraints."""
    orch = FakeOrchestrator()
    res = orch.run(
        question="How many fencing events at the 2008 Summer Olympics had more than 32 competitors?",
        question_id="pub-027",
    )
    assert res.pipeline == "agentic"
    assert len(res.trace) > 0
    assert res.trace[-1].decision == "stop"
    assert res.stop_reason is not None
    assert res.tokens.total_tokens == res.tokens.llm_input_tokens + res.tokens.llm_output_tokens
    assert res.tokens.context_tokens <= res.tokens.llm_input_tokens
    assert len(res.citations) > 0
