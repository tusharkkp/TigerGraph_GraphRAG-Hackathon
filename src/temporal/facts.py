"""
Temporal Fact Modeling for Olympic GraphRAG Systems.

Represents temporal claims and assertions with explicit validity windows,
source authority scores, and provenance linkages.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field


class Fact(BaseModel):
    """A single atomic assertion grounded in Olympic corpus chunks."""
    fact_id: str = Field(default_factory=lambda: f"fact-{uuid.uuid4().hex[:8]}")
    subject: str = Field(..., description="Subject entity or event, e.g. 'Men's 100 metres 2004'")
    predicate: str = Field(..., description="Relation/attribute, e.g. 'gold_medalist', 'competitors'")
    value: Any = Field(..., description="Value asserted, e.g. 'Justin Gatlin', 32")
    valid_from: Optional[str] = Field(None, description="ISO date or Olympic year start")
    valid_to: Optional[str] = Field(None, description="ISO date or Olympic year end if revoked/superseded")
    asserted_at: Optional[str] = Field(None, description="Timestamp or publication context")
    source_chunk_id: str = Field(..., description="Chunk ID providing provenance")
    source_doc_id: str = Field(..., description="Document ID")
    source_authority: float = Field(default=0.8, ge=0.0, le=1.0, description="Authority score of source")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    revision_marker: Optional[str] = Field(
        None,
        description="e.g. 'disqualified', 'stripped', 'reallocated', 'postponed', 'revised'"
    )
    supersedes_fact_id: Optional[str] = None
    conflict_ids: list[str] = Field(default_factory=list)


class FactStore:
    """In-memory store of extracted facts indexed by (subject, predicate)."""

    def __init__(self):
        self.facts: dict[str, Fact] = {}
        self.by_claim_key: dict[tuple[str, str], list[str]] = {}

    def add_fact(self, fact: Fact) -> None:
        self.facts[fact.fact_id] = fact
        key = (fact.subject.lower().strip(), fact.predicate.lower().strip())
        self.by_claim_key.setdefault(key, []).append(fact.fact_id)

    def get_facts_for_claim(self, subject: str, predicate: str) -> list[Fact]:
        key = (subject.lower().strip(), predicate.lower().strip())
        fact_ids = self.by_claim_key.get(key, [])
        return [self.facts[fid] for fid in fact_ids]

    def all_claims(self) -> list[tuple[str, str]]:
        return list(self.by_claim_key.keys())
