"""Unit tests for contracts, config, and splits — no network required."""

import json
from pathlib import Path

import pytest
from src.contracts import (
    PipelineResult,
    Question,
    TokenUsage,
    TraceStep,
)

# ---------------------------------------------------------------------------
# TokenUsage invariants
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_valid_usage(self):
        t = TokenUsage(context_tokens=100, llm_input_tokens=500, llm_output_tokens=200, total_tokens=700)
        assert t.total_tokens == 700

    def test_total_must_equal_sum(self):
        with pytest.raises(ValueError, match="total_tokens"):
            TokenUsage(context_tokens=100, llm_input_tokens=500, llm_output_tokens=200, total_tokens=999)

    def test_context_cannot_exceed_input(self):
        with pytest.raises(ValueError, match="context_tokens"):
            TokenUsage(context_tokens=600, llm_input_tokens=500, llm_output_tokens=200, total_tokens=700)

    def test_zero_tokens_valid(self):
        t = TokenUsage(context_tokens=0, llm_input_tokens=0, llm_output_tokens=0, total_tokens=0)
        assert t.total_tokens == 0


# ---------------------------------------------------------------------------
# PipelineResult constraints
# ---------------------------------------------------------------------------


class TestPipelineResult:
    def _make_tokens(self, **overrides):
        defaults = dict(context_tokens=100, llm_input_tokens=500, llm_output_tokens=200, total_tokens=700)
        defaults.update(overrides)
        return TokenUsage(**defaults)

    def _make_trace_step(self, step=0, decision="stop"):
        return TraceStep(
            step=step,
            agent="test",
            tool="test_tool",
            args={},
            rationale="testing",
            observation_summary="observed",
            tokens_in=100,
            tokens_out=50,
            latency_ms=100,
            strategy_tag="test",
            decision=decision,
        )

    def test_rag_must_have_empty_trace(self):
        with pytest.raises(ValueError, match="RAG pipeline must have an empty trace"):
            PipelineResult(
                question_id="q1",
                pipeline="rag",
                answer="test",
                tokens=self._make_tokens(),
                latency_ms=100,
                trace=[self._make_trace_step()],
            )

    def test_rag_valid(self):
        r = PipelineResult(
            question_id="q1",
            pipeline="rag",
            answer="test answer",
            tokens=self._make_tokens(),
            latency_ms=100,
        )
        assert r.trace == []

    def test_agentic_must_have_trace(self):
        with pytest.raises(ValueError, match="Agentic pipeline must have a non-empty trace"):
            PipelineResult(
                question_id="q1",
                pipeline="agentic",
                answer="test",
                tokens=self._make_tokens(),
                latency_ms=100,
            )

    def test_agentic_must_have_stop_reason(self):
        with pytest.raises(ValueError, match="stop_reason"):
            PipelineResult(
                question_id="q1",
                pipeline="agentic",
                answer="test",
                tokens=self._make_tokens(),
                latency_ms=100,
                trace=[self._make_trace_step(decision="stop")],
            )

    def test_agentic_last_step_must_be_stop(self):
        with pytest.raises(ValueError, match="decision='stop'"):
            PipelineResult(
                question_id="q1",
                pipeline="agentic",
                answer="test",
                tokens=self._make_tokens(),
                latency_ms=100,
                stop_reason="sufficient",
                trace=[self._make_trace_step(decision="continue")],
            )

    def test_agentic_valid(self):
        r = PipelineResult(
            question_id="q1",
            pipeline="agentic",
            answer="test",
            tokens=self._make_tokens(),
            latency_ms=100,
            stop_reason="sufficient_evidence",
            trace=[
                self._make_trace_step(step=0, decision="continue"),
                self._make_trace_step(step=1, decision="stop"),
            ],
        )
        assert len(r.trace) == 2
        assert r.stop_reason == "sufficient_evidence"

    def test_agentic_with_error_skips_trace_validation(self):
        """An errored agentic result can have empty trace."""
        r = PipelineResult(
            question_id="q1",
            pipeline="agentic",
            answer="",
            tokens=self._make_tokens(),
            latency_ms=100,
            error="LLM call failed",
        )
        assert r.error == "LLM call failed"

    def test_graphrag_allows_basic_trace(self):
        """GraphRAG can have a basic trace (not required but allowed)."""
        r = PipelineResult(
            question_id="q1",
            pipeline="graphrag",
            answer="test",
            tokens=self._make_tokens(),
            latency_ms=100,
        )
        assert r.pipeline == "graphrag"


# ---------------------------------------------------------------------------
# Question model
# ---------------------------------------------------------------------------


class TestQuestion:
    def test_public_question(self):
        q = Question(
            qid="pub-001",
            question="How many events?",
            qtype="aggregation",
            answer=["5"],
            gold_doc_ids=["Q1", "Q2"],
            answer_named_in_question=False,
            guess_baseline=0.0,
            answer_verified=True,
        )
        assert q.answer == ["5"]

    def test_hidden_question(self):
        q = Question(qid="eval-001", question="Who won?", qtype="multi_hop")
        assert q.answer is None
        assert q.gold_doc_ids is None


# ---------------------------------------------------------------------------
# TraceStep decisions
# ---------------------------------------------------------------------------


class TestTraceStep:
    def test_valid_decisions(self):
        for d in ["continue", "change_strategy", "stop"]:
            step = TraceStep(
                step=0, agent="a", tool="t", rationale="r", observation_summary="o",
                tokens_in=0, tokens_out=0, latency_ms=0, strategy_tag="s", decision=d,
            )
            assert step.decision == d

    def test_invalid_decision(self):
        with pytest.raises(ValueError):
            TraceStep(
                step=0, agent="a", tool="t", rationale="r", observation_summary="o",
                tokens_in=0, tokens_out=0, latency_ms=0, strategy_tag="s", decision="invalid",
            )


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


class TestSplits:
    @pytest.fixture
    def splits(self):
        path = Path(__file__).resolve().parent.parent.parent / "data" / "splits.json"
        with open(path) as f:
            return json.load(f)

    def test_seed_is_42(self, splits):
        assert splits["seed"] == 42

    def test_counts(self, splits):
        assert splits["counts"]["dev"] == 60
        assert splits["counts"]["val"] == 20
        assert splits["counts"]["test"] == 20

    def test_no_overlap(self, splits):
        dev = set(splits["splits"]["dev"])
        val = set(splits["splits"]["val"])
        test = set(splits["splits"]["test"])
        assert not (dev & val), "dev/val overlap"
        assert not (dev & test), "dev/test overlap"
        assert not (val & test), "val/test overlap"

    def test_all_100_present(self, splits):
        all_ids = (
            set(splits["splits"]["dev"])
            | set(splits["splits"]["val"])
            | set(splits["splits"]["test"])
        )
        assert len(all_ids) == 100

    def test_no_hidden_ids_in_splits(self, splits):
        hidden_path = Path(__file__).resolve().parent.parent.parent / "Dataset" / "questions" / "eval_hidden.jsonl"
        hidden_ids = set()
        with open(hidden_path) as f:
            for line in f:
                hidden_ids.add(json.loads(line.strip())["qid"])

        all_ids = (
            set(splits["splits"]["dev"])
            | set(splits["splits"]["val"])
            | set(splits["splits"]["test"])
        )
        assert not (all_ids & hidden_ids), "Hidden question IDs found in splits!"

    def test_stratified_by_type(self, splits):
        """Each split should have all 5 question types."""
        for split_name in ["dev", "val", "test"]:
            types = splits["type_distribution"][split_name]
            assert len(types) == 5, f"{split_name} missing question types: {types}"
