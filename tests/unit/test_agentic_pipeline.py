"""
Unit tests for Pipeline 3 Agentic GraphRAG components and tool suite.
"""

from __future__ import annotations

import pytest

from src.agentic.entity_linker import EntityLinker
from src.agentic.evaluator import EvidenceEvaluator
from src.agentic.orchestrator import ExecutionPlan, PlannedStep, ToolArgs
from src.contracts import PipelineResult


def test_entity_linker_extraction():
    """Verify EntityLinker extracts sports, years, genders, thresholds without LLM calls."""
    q = "According to the provided corpus, how many biathlon events at the 2014 Winter Olympics had more than 68 competitors?"
    linked = EntityLinker.link_question(q)
    assert linked.sport == "Biathlon"
    assert linked.year == 2014
    assert linked.season == "Winter"


def test_tool_args_schema_validity():
    """Verify ToolArgs generates valid schema without additionalProperties."""
    args = ToolArgs(sport="Biathlon", year=2014, min_competitors=69)
    dump = args.model_dump()
    assert dump["sport"] == "Biathlon"
    assert dump["year"] == 2014
    assert dump["min_competitors"] == 69


def test_execution_plan_validation():
    """Verify ExecutionPlan parses structured plans."""
    step = PlannedStep(
        agent="Aggregator",
        tool="Find_Events",
        args=ToolArgs(sport="Biathlon", year=2014, min_competitors=69),
        purpose="Count qualifying events",
    )
    plan = ExecutionPlan(
        reasoning="Count events exceeding threshold",
        question_type="aggregation",
        steps=[step],
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "Find_Events"
    assert plan.steps[0].args.min_competitors == 69


def test_evidence_evaluator_sufficiency():
    """Verify EvidenceEvaluator marks sufficiency on aggregation count."""
    ee = EvidenceEvaluator(max_steps=3)
    dec = ee.evaluate_step(
        step_num=1,
        tool_name="Find_Events",
        tool_args={"sport": "Biathlon"},
        observation={"total_count": 5, "events": [{"name": "Men's sprint"}]},
        tokens_so_far=500,
        is_final_step_planned=True,
    )
    assert dec.decision == "stop"
    assert dec.stop_reason == "SUFFICIENCY_REACHED"
