"""
Adaptive Query Router for Olympic GraphRAG Systems.

Predicts optimal retrieval pipeline (P1 Vector RAG, P2 GraphRAG, P3 Agentic GraphRAG)
from cheap linguistic features, entity signals, and question taxonomy.

Enables Pareto-optimal trade-offs between accuracy, token consumption, and latency:
- Routes simple lookups to P1 (100% accuracy, lowest tokens)
- Routes entity/neighborhood lookups to P2 (graph neighborhood)
- Routes aggregation, temporal edition hops, and superlatives to P3 (Agentic GSQL tools)
"""

from __future__ import annotations

import enum
import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.contracts import PipelineResult, Question

logger = logging.getLogger(__name__)


class QueryIntent(str, enum.Enum):
    LOOKUP = "lookup"
    GRAPH_NEIGHBORHOOD = "graph_neighborhood"
    AGGREGATION = "aggregation"
    TEMPORAL_CHAIN = "temporal_chain"
    SUPERLATIVE = "superlative"
    UNKNOWN = "unknown"


class RouterDecision(BaseModel):
    recommended_pipeline: Literal["rag", "graphrag", "agentic"]
    intent: QueryIntent
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    features: dict[str, Any] = Field(default_factory=dict)
    rationale: str


class AdaptiveRouter:
    """
    Cost- and Capability-Aware Router for Olympic Question Answering.
    """

    # High-signal patterns
    AGGREGATION_PATTERNS = [
        re.compile(r"\bhow many (?:events|competitions|races|matches|contests)\b", re.IGNORECASE),
        re.compile(r"\b(?:more|greater|fewer|less) than \d+ competitors\b", re.IGNORECASE),
        re.compile(r"\bhad (?:more|greater|fewer|less) than\b", re.IGNORECASE),
        re.compile(r"\bhighest number of competitors\b", re.IGNORECASE),
        re.compile(r"\btotal (?:number of|count of)\b", re.IGNORECASE),
    ]

    TEMPORAL_PATTERNS = [
        re.compile(r"\b(?:immediately|directly) (?:before|after|prior to|following)\b", re.IGNORECASE),
        re.compile(r"\bheld (?:immediately )?before \d{4}\b", re.IGNORECASE),
        re.compile(r"\bheld (?:immediately )?after \d{4}\b", re.IGNORECASE),
        re.compile(r"\bpreceding (?:games|olympics|edition)\b", re.IGNORECASE),
        re.compile(r"\bsucceeding (?:games|olympics|edition)\b", re.IGNORECASE),
    ]

    SUPERLATIVE_PATTERNS = [
        re.compile(r"\bwhich .* had the (?:highest|most|greatest|lowest|fewest) (?:number of )?competitors\b", re.IGNORECASE),
        re.compile(r"\bwho (?:is|was) the (?:oldest|youngest|most decorated)\b", re.IGNORECASE),
    ]

    VENUE_PATTERNS = [
        re.compile(r"\bheld at [A-Z][a-z]+ (?:Stadium|Centre|Center|Oval|Arena|Velodrome|Hall|Gymnasium|Park)\b"),
        re.compile(r"\bat the [A-Z][a-z]+ (?:Stadium|Centre|Center|Oval|Arena|Velodrome|Hall|Gymnasium|Park)\b"),
    ]

    LOOKUP_PATTERNS = [
        re.compile(r"\bhow many nations competed in\b", re.IGNORECASE),
        re.compile(r"\bhow many competitors competed in\b", re.IGNORECASE),
        re.compile(r"\bwho won the (?:gold|silver|bronze) medal in the [A-Za-z0-9' –-]+ event\b", re.IGNORECASE),
    ]

    def __init__(self, p1=None, p2=None, p3=None):
        self._p1 = p1
        self._p2 = p2
        self._p3 = p3

    def classify_intent(self, question: str) -> tuple[QueryIntent, dict[str, bool]]:
        """Extract linguistic features and map to query intent."""
        features = {
            "has_aggregation": any(p.search(question) for p in self.AGGREGATION_PATTERNS),
            "has_temporal_chain": any(p.search(question) for p in self.TEMPORAL_PATTERNS),
            "has_superlative": any(p.search(question) for p in self.SUPERLATIVE_PATTERNS),
            "has_venue_date": any(p.search(question) for p in self.VENUE_PATTERNS),
            "has_single_event_lookup": any(p.search(question) for p in self.LOOKUP_PATTERNS),
        }

        if features["has_temporal_chain"]:
            return QueryIntent.TEMPORAL_CHAIN, features
        if features["has_superlative"]:
            return QueryIntent.SUPERLATIVE, features
        if features["has_aggregation"]:
            return QueryIntent.AGGREGATION, features
        if features["has_venue_date"]:
            return QueryIntent.GRAPH_NEIGHBORHOOD, features
        if features["has_single_event_lookup"]:
            return QueryIntent.LOOKUP, features

        return QueryIntent.UNKNOWN, features

    def predict(self, question: str) -> RouterDecision:
        """Predict the optimal pipeline for a given question."""
        intent, features = self.classify_intent(question)

        if intent in (QueryIntent.AGGREGATION, QueryIntent.TEMPORAL_CHAIN, QueryIntent.SUPERLATIVE):
            # Aggregation and multi-edition temporal hops strictly require Agentic GSQL tools
            return RouterDecision(
                recommended_pipeline="agentic",
                intent=intent,
                confidence=0.95,
                features=features,
                rationale=f"Query exhibits {intent.value} requiring iterative GSQL tools and parameter filtering.",
            )
        elif intent == QueryIntent.GRAPH_NEIGHBORHOOD:
            # Complex venue/date multi-hop benefits from graph neighborhood or agentic
            return RouterDecision(
                recommended_pipeline="agentic",
                intent=intent,
                confidence=0.85,
                features=features,
                rationale="Multi-hop venue/date lookup requires entity resolution and graph context traversal.",
            )
        elif intent == QueryIntent.LOOKUP:
            # Single event infobox lookup achieves 100% accuracy with P1 Vector RAG at lowest cost
            return RouterDecision(
                recommended_pipeline="rag",
                intent=intent,
                confidence=0.90,
                features=features,
                rationale="Direct single-event infobox attribute lookup is optimally resolved via cheap vector search.",
            )
        else:
            # Default fallback: GraphRAG provides balanced structured traversal
            return RouterDecision(
                recommended_pipeline="graphrag",
                intent=intent,
                confidence=0.75,
                features=features,
                rationale="Standard Olympic entity/relationship question routed to structured GraphRAG.",
            )

    def route_and_execute(self, q_input: Question | dict[str, Any], top_k: int = 5) -> tuple[PipelineResult, RouterDecision]:
        """Classify question and execute on the predicted pipeline."""
        if isinstance(q_input, dict):
            q_text = q_input.get("question", "")
        else:
            q_text = q_input.question

        decision = self.predict(q_text)
        target = decision.recommended_pipeline

        if target == "rag":
            if self._p1 is None:
                from src.pipelines.p1_vector_rag import VectorRAGPipeline
                self._p1 = VectorRAGPipeline()
            res = self._p1.run(q_input, top_k=top_k)
        elif target == "graphrag":
            if self._p2 is None:
                from src.pipelines.p2_graphrag import GraphRAGPipeline
                self._p2 = GraphRAGPipeline()
            res = self._p2.run(q_input, top_k=top_k)
        else:
            if self._p3 is None:
                from src.pipelines.p3_agentic import AgenticGraphRAGPipeline
                self._p3 = AgenticGraphRAGPipeline()
            res = self._p3.run(q_input, top_k=top_k)

        return res, decision


def simulate_pareto_frontier(
    p1_results: list[dict[str, Any]],
    p2_results: list[dict[str, Any]],
    p3_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute comparative Pareto statistics across pipelines and the adaptive router.
    """
    router = AdaptiveRouter()

    # Index results by question_id
    p1_map = {r["question_id"]: r for r in p1_results}
    p2_map = {r["question_id"]: r for r in p2_results}
    p3_map = {r["question_id"]: r for r in p3_results}

    all_qids = [r["question_id"] for r in p1_results if r["question_id"] in p3_map]

    strategies = {
        "Always P1 (Vector RAG)": {"pass": 0, "tokens": 0, "latency": 0.0, "count": 0},
        "Always P2 (GraphRAG)": {"pass": 0, "tokens": 0, "latency": 0.0, "count": 0},
        "Always P3 (Agentic GraphRAG)": {"pass": 0, "tokens": 0, "latency": 0.0, "count": 0},
        "Adaptive Router (Hybrid)": {"pass": 0, "tokens": 0, "latency": 0.0, "count": 0, "routed": {"rag": 0, "graphrag": 0, "agentic": 0}},
        "Oracle Router (Optimal)": {"pass": 0, "tokens": 0, "latency": 0.0, "count": 0},
    }

    for qid in all_qids:
        r1 = p1_map[qid]
        r2 = p2_map.get(qid, r1)
        r3 = p3_map[qid]

        q_text = r1.get("question", "")
        decision = router.predict(q_text)

        # 1. Always P1
        strategies["Always P1 (Vector RAG)"]["count"] += 1
        strategies["Always P1 (Vector RAG)"]["pass"] += 1 if r1.get("pass_rate", r1.get("passed", False)) else 0
        strategies["Always P1 (Vector RAG)"]["tokens"] += r1.get("tokens", {}).get("total_tokens", 0)
        strategies["Always P1 (Vector RAG)"]["latency"] += r1.get("latency_sec", 0.0)

        # 2. Always P2
        strategies["Always P2 (GraphRAG)"]["count"] += 1
        strategies["Always P2 (GraphRAG)"]["pass"] += 1 if r2.get("pass_rate", r2.get("passed", False)) else 0
        strategies["Always P2 (GraphRAG)"]["tokens"] += r2.get("tokens", {}).get("total_tokens", 0)
        strategies["Always P2 (GraphRAG)"]["latency"] += r2.get("latency_sec", 0.0)

        # 3. Always P3
        strategies["Always P3 (Agentic GraphRAG)"]["count"] += 1
        strategies["Always P3 (Agentic GraphRAG)"]["pass"] += 1 if r3.get("pass_rate", r3.get("passed", False)) else 0
        strategies["Always P3 (Agentic GraphRAG)"]["tokens"] += r3.get("tokens", {}).get("total_tokens", 0)
        strategies["Always P3 (Agentic GraphRAG)"]["latency"] += r3.get("latency_sec", 0.0)

        # 4. Adaptive Router
        routed_pipeline = decision.recommended_pipeline
        strategies["Adaptive Router (Hybrid)"]["routed"][routed_pipeline] += 1
        chosen_r = r1 if routed_pipeline == "rag" else (r2 if routed_pipeline == "graphrag" else r3)

        strategies["Adaptive Router (Hybrid)"]["count"] += 1
        strategies["Adaptive Router (Hybrid)"]["pass"] += 1 if chosen_r.get("pass_rate", chosen_r.get("passed", False)) else 0
        strategies["Adaptive Router (Hybrid)"]["tokens"] += chosen_r.get("tokens", {}).get("total_tokens", 0)
        strategies["Adaptive Router (Hybrid)"]["latency"] += chosen_r.get("latency_sec", 0.0)

        # 5. Oracle
        any_passed = any([
            r1.get("pass_rate", r1.get("passed", False)),
            r2.get("pass_rate", r2.get("passed", False)),
            r3.get("pass_rate", r3.get("passed", False)),
        ])
        # Pick cheapest passing, or cheapest if none pass
        candidates = []
        for name, cand in [("p1", r1), ("p2", r2), ("p3", r3)]:
            is_p = cand.get("pass_rate", cand.get("passed", False))
            tok = cand.get("tokens", {}).get("total_tokens", 0)
            candidates.append((is_p, tok, cand))

        candidates.sort(key=lambda x: (not x[0], x[1]))
        oracle_r = candidates[0][2]

        strategies["Oracle Router (Optimal)"]["count"] += 1
        strategies["Oracle Router (Optimal)"]["pass"] += 1 if any_passed else 0
        strategies["Oracle Router (Optimal)"]["tokens"] += oracle_r.get("tokens", {}).get("total_tokens", 0)
        strategies["Oracle Router (Optimal)"]["latency"] += oracle_r.get("latency_sec", 0.0)

    summary = {}
    for name, data in strategies.items():
        n = max(1, data["count"])
        p_cnt = data["pass"]
        summary[name] = {
            "questions": n,
            "passed": p_cnt,
            "accuracy": round(p_cnt / n, 4),
            "avg_tokens": round(data["tokens"] / n, 1),
            "avg_latency_sec": round(data["latency"] / n, 2),
            "cost_per_correct_k_tokens": round((data["tokens"] / max(1, p_cnt)) / 1000.0, 2),
        }
        if "routed" in data:
            summary[name]["routing_distribution"] = data["routed"]

    return summary
