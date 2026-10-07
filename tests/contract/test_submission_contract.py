"""
Contract tests verifying submission schema compliance and invariants.
"""

from __future__ import annotations

import json
import pytest

from src.contracts import Citation, PipelineResult, TokenUsage, TraceStep


def test_submission_contract_model_dump():
    tokens = TokenUsage(
        context_tokens=1500,
        llm_input_tokens=2000,
        llm_output_tokens=150,
        total_tokens=2150,
    )
    citation = Citation(
        chunk_id="Q100_c000",
        doc_id="Q100",
        quote="Exact quote excerpt",
        entity_ids=["Athlete_Usain_Bolt"],
    )
    step1 = TraceStep(
        step=1,
        agent="orchestrator",
        tool="Find_Events",
        args={"sport": "Athletics", "year": 2008},
        rationale="Looking for Athletics events in 2008",
        observation_summary="Found 12 events",
        new_evidence_ids=["event-1"],
        tokens_in=250,
        tokens_out=40,
        latency_ms=120,
        strategy_tag="graph_first",
        decision="continue",
    )
    step2 = TraceStep(
        step=2,
        agent="orchestrator",
        tool="Event_Details",
        args={"event_id": "event-1"},
        rationale="Retrieved gold medalist details",
        observation_summary="Usain Bolt won gold",
        new_evidence_ids=["fact-1"],
        tokens_in=200,
        tokens_out=30,
        latency_ms=90,
        strategy_tag="graph_first",
        decision="stop",
    )
    res = PipelineResult(
        question_id="eval-001",
        pipeline="agentic",
        answer="Usain Bolt",
        citations=[citation],
        retrieved_chunk_ids=["Q100_c000"],
        tokens=tokens,
        latency_ms=1200,
        trace=[step1, step2],
        stop_reason="sufficient_evidence",
    )

    # Validate output dictionary matching export format
    rec = {
        "question_id": res.question_id,
        "question": "Who won gold?",
        "answer": res.answer,
        "tokens": res.tokens.model_dump(),
        "latency_sec": round(res.latency_ms / 1000.0, 3),
        "trace": [t.model_dump() for t in res.trace],
        "citations": [c.model_dump() for c in res.citations],
    }

    # Serialization roundtrip
    dumped = json.dumps(rec)
    loaded = json.loads(dumped)

    assert loaded["question_id"] == "eval-001"
    assert loaded["answer"] == "Usain Bolt"
    assert loaded["tokens"]["total_tokens"] == 2150
    assert loaded["tokens"]["total_tokens"] == loaded["tokens"]["llm_input_tokens"] + loaded["tokens"]["llm_output_tokens"]
    assert loaded["citations"][0]["chunk_id"] == "Q100_c000"
    assert loaded["citations"][0]["quote"] == "Exact quote excerpt"
    assert len(loaded["trace"]) == 2
    assert loaded["trace"][0]["decision"] == "continue"
    assert loaded["trace"][1]["decision"] == "stop"
