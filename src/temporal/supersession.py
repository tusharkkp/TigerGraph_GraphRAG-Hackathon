"""
Supersession and Conflict Resolution for Olympic Temporal Facts.

Implements rule-based, deterministic resolution policies:
1. Retroactive revision & disqualification (stripping/reallocation supersedes original)
2. Source authority weighting (official infobox/tables > general body text)
3. Recency of assertion/validity
4. Corroboration plurality

Produces structured explainable resolutions with calibrated uncertainty.
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from pydantic import BaseModel, Field

from src.temporal.conflicts import ConflictDetector, ConflictType
from src.temporal.facts import Fact

logger = logging.getLogger(__name__)


class ResolvedFact(BaseModel):
    subject: str
    predicate: str
    active_value: Any
    superseded_values: list[Any] = Field(default_factory=list)
    conflicting_sources: list[str] = Field(default_factory=list)
    resolution_rationale: str
    calibrated_uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["uncontested", "resolved", "unresolvable"]
    winning_fact: Fact


class SupersessionResolver:
    """Deterministic, policy-driven fact supersession engine."""

    def __init__(self):
        self.detector = ConflictDetector()

    def resolve_claim(self, facts: list[Fact]) -> ResolvedFact:
        if not facts:
            raise ValueError("Cannot resolve empty fact list")

        subject = facts[0].subject
        predicate = facts[0].predicate

        if len(facts) == 1:
            return ResolvedFact(
                subject=subject,
                predicate=predicate,
                active_value=facts[0].value,
                resolution_rationale="Single uncontested observation in corpus.",
                calibrated_uncertainty=0.0,
                status="uncontested",
                winning_fact=facts[0],
            )

        # Detect any conflicts
        conflicts = self.detector.detect_conflicts_for_claim(facts)
        if not conflicts:
            # All facts agree on value
            return ResolvedFact(
                subject=subject,
                predicate=predicate,
                active_value=facts[0].value,
                resolution_rationale=f"Corroborated across {len(facts)} sources without disagreement.",
                calibrated_uncertainty=0.0,
                status="uncontested",
                winning_fact=facts[0],
            )

        # Collect distinct values and sources
        all_values = list({f.value for f in facts})
        all_sources = list({f.source_chunk_id for f in facts})

        # Policy 1: Explicit Revision / Retroactive Disqualification
        revision_facts = [
            f for f in facts
            if f.revision_marker or any(
                m in str(f.value).lower() for m in ["disqualified", "stripped", "reallocated", "vacated", "revised"]
            )
        ]

        if revision_facts:
            # Sort by authority then recency
            revision_facts.sort(key=lambda x: (x.source_authority, str(x.asserted_at or "")), reverse=True)
            winner = revision_facts[0]
            superseded = [v for v in all_values if str(v).lower() != str(winner.value).lower()]
            winner.supersedes_fact_id = facts[0].fact_id

            return ResolvedFact(
                subject=subject,
                predicate=predicate,
                active_value=winner.value,
                superseded_values=superseded,
                conflicting_sources=all_sources,
                resolution_rationale=f"Policy 1 (Status Revision): Official retroactive revision ('{winner.revision_marker or winner.value}') supersedes prior preliminary status.",
                calibrated_uncertainty=0.05,
                status="resolved",
                winning_fact=winner,
            )

        # Policy 2: Source Authority (Infobox/structured vs narrative)
        # Group by value and calculate max authority and corroboration score
        val_scores: dict[str, dict[str, Any]] = {}
        for f in facts:
            val_key = str(f.value).strip().lower()
            if val_key not in val_scores:
                val_scores[val_key] = {
                    "original_val": f.value,
                    "max_authority": f.source_authority,
                    "count": 1,
                    "best_fact": f,
                }
            else:
                val_scores[val_key]["count"] += 1
                if f.source_authority > val_scores[val_key]["max_authority"]:
                    val_scores[val_key]["max_authority"] = f.source_authority
                    val_scores[val_key]["best_fact"] = f

        sorted_candidates = sorted(
            val_scores.values(),
            key=lambda x: (x["max_authority"], x["count"]),
            reverse=True,
        )

        top_cand = sorted_candidates[0]
        runner_up = sorted_candidates[1] if len(sorted_candidates) > 1 else None

        if runner_up and (top_cand["max_authority"] > runner_up["max_authority"] + 0.15):
            winner = top_cand["best_fact"]
            superseded = [c["original_val"] for c in sorted_candidates if c != top_cand]
            return ResolvedFact(
                subject=subject,
                predicate=predicate,
                active_value=winner.value,
                superseded_values=superseded,
                conflicting_sources=all_sources,
                resolution_rationale=f"Policy 2 (Authority): High-authority source ({winner.source_authority:.2f}) supersedes lower-authority conflicting assertions ({runner_up['max_authority']:.2f}).",
                calibrated_uncertainty=0.15,
                status="resolved",
                winning_fact=winner,
            )

        # Policy 3: Corroboration Plurality
        if runner_up and (top_cand["count"] > runner_up["count"]):
            winner = top_cand["best_fact"]
            superseded = [c["original_val"] for c in sorted_candidates if c != top_cand]
            return ResolvedFact(
                subject=subject,
                predicate=predicate,
                active_value=winner.value,
                superseded_values=superseded,
                conflicting_sources=all_sources,
                resolution_rationale=f"Policy 3 (Plurality): Corroborated by {top_cand['count']} independent sources vs {runner_up['count']} for competing claim.",
                calibrated_uncertainty=0.25,
                status="resolved",
                winning_fact=winner,
            )

        # Ties: Unresolvable with high uncertainty
        winner = top_cand["best_fact"]
        return ResolvedFact(
            subject=subject,
            predicate=predicate,
            active_value=f"Conflicting: {top_cand['original_val']} vs {runner_up['original_val'] if runner_up else 'unknown'}",
            superseded_values=[],
            conflicting_sources=all_sources,
            resolution_rationale="Conflicting claims have equal authority and equal corroboration count; unresolvable without external primary evidence.",
            calibrated_uncertainty=0.85,
            status="unresolvable",
            winning_fact=winner,
        )
