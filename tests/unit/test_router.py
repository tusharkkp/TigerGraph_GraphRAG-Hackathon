"""
Unit tests for the Adaptive Query Router.
"""

from __future__ import annotations

import pytest

from src.eval.router import AdaptiveRouter, QueryIntent, RouterDecision, simulate_pareto_frontier


def test_router_classification():
    router = AdaptiveRouter()

    # Aggregation
    q_agg = "According to the provided corpus, how many cycling events at the 2000 Summer Olympics had more than 30 competitors?"
    dec_agg = router.predict(q_agg)
    assert dec_agg.recommended_pipeline == "agentic"
    assert dec_agg.intent == QueryIntent.AGGREGATION

    # Temporal chain
    q_temp = "Who won the gold medal in the women's 200 metres athletics event at the Summer Olympics held immediately before 2016?"
    dec_temp = router.predict(q_temp)
    assert dec_temp.recommended_pipeline == "agentic"
    assert dec_temp.intent == QueryIntent.TEMPORAL_CHAIN

    # Superlative
    q_sup = "According to the provided corpus, which weightlifting event at the 1992 Summer Olympics had the highest number of competitors?"
    dec_sup = router.predict(q_sup)
    assert dec_sup.recommended_pipeline == "agentic"
    assert dec_sup.intent == QueryIntent.SUPERLATIVE

    # Lookup
    q_look = "How many nations competed in Sailing at the 2016 Summer Olympics – Women's RS:X?"
    dec_look = router.predict(q_look)
    assert dec_look.recommended_pipeline == "rag"
    assert dec_look.intent == QueryIntent.LOOKUP


def test_simulate_pareto_frontier():
    p1_mock = [
        {"question_id": "q1", "question": "How many nations competed in Sailing?", "passed": True, "tokens": {"total_tokens": 1000}, "latency_sec": 1.0},
        {"question_id": "q2", "question": "How many cycling events had more than 30 competitors?", "passed": False, "tokens": {"total_tokens": 1000}, "latency_sec": 1.0},
    ]
    p2_mock = [
        {"question_id": "q1", "question": "How many nations competed in Sailing?", "passed": True, "tokens": {"total_tokens": 1500}, "latency_sec": 2.0},
        {"question_id": "q2", "question": "How many cycling events had more than 30 competitors?", "passed": False, "tokens": {"total_tokens": 1500}, "latency_sec": 2.0},
    ]
    p3_mock = [
        {"question_id": "q1", "question": "How many nations competed in Sailing?", "passed": True, "tokens": {"total_tokens": 2500}, "latency_sec": 5.0},
        {"question_id": "q2", "question": "How many cycling events had more than 30 competitors?", "passed": True, "tokens": {"total_tokens": 2500}, "latency_sec": 5.0},
    ]

    summary = simulate_pareto_frontier(p1_mock, p2_mock, p3_mock)

    assert "Always P1 (Vector RAG)" in summary
    assert "Always P2 (GraphRAG)" in summary
    assert "Always P3 (Agentic GraphRAG)" in summary
    assert "Adaptive Router (Hybrid)" in summary
    assert "Oracle Router (Optimal)" in summary

    # Adaptive router routes q1 to P1 and q2 to P3, so both pass!
    assert summary["Adaptive Router (Hybrid)"]["accuracy"] == 1.0
    # Average tokens of adaptive: (1000 + 2500) / 2 = 1750, less than always P3 (2500)!
    assert summary["Adaptive Router (Hybrid)"]["avg_tokens"] == 1750.0
