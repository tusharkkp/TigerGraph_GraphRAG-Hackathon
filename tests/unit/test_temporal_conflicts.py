"""
Unit tests for Temporal Fact Modeling, Conflict Detection, and Supersession Resolution.
"""

from __future__ import annotations

import pytest

from src.temporal.conflicts import ConflictDetector, ConflictType
from src.temporal.facts import Fact, FactStore
from src.temporal.supersession import SupersessionResolver


def test_fact_store_and_uncontested_resolution():
    store = FactStore()
    f1 = Fact(
        subject="Athletics Men's 100m 2008",
        predicate="gold_medalist",
        value="Usain Bolt",
        source_chunk_id="c001",
        source_doc_id="d001",
        source_authority=0.95,
    )
    store.add_fact(f1)

    resolver = SupersessionResolver()
    res = resolver.resolve_claim(store.get_facts_for_claim("Athletics Men's 100m 2008", "gold_medalist"))
    assert res.status == "uncontested"
    assert res.active_value == "Usain Bolt"
    assert res.calibrated_uncertainty == 0.0


def test_status_revision_disqualification_supersession():
    # Scenario: Original gold medalist stripped for doping, reallocated
    f_orig = Fact(
        subject="Men's 50km Walk 2012",
        predicate="gold_medalist",
        value="Sergey Kirdyapkin",
        source_chunk_id="c100",
        source_doc_id="d100",
        source_authority=0.7,
        asserted_at="2012-08-11",
    )
    f_rev = Fact(
        subject="Men's 50km Walk 2012",
        predicate="gold_medalist",
        value="Jared Tallent",
        source_chunk_id="c101",
        source_doc_id="d101",
        source_authority=0.95,
        asserted_at="2016-03-24",
        revision_marker="disqualified/reallocated",
    )

    resolver = SupersessionResolver()
    res = resolver.resolve_claim([f_orig, f_rev])

    assert res.status == "resolved"
    assert res.active_value == "Jared Tallent"
    assert "Sergey Kirdyapkin" in res.superseded_values
    assert res.calibrated_uncertainty <= 0.1
    assert "Policy 1" in res.resolution_rationale


def test_authority_conflict_resolution():
    # Scenario: Wikipedia talk/commentary claim (0.5 authority) vs official infobox (0.95 authority)
    f_low = Fact(
        subject="Cycling Men's Sprint 2004",
        predicate="competitors",
        value=18,
        source_chunk_id="c201",
        source_doc_id="d201",
        source_authority=0.5,
    )
    f_high = Fact(
        subject="Cycling Men's Sprint 2004",
        predicate="competitors",
        value=19,
        source_chunk_id="c202",
        source_doc_id="d202",
        source_authority=0.95,
    )

    resolver = SupersessionResolver()
    res = resolver.resolve_claim([f_low, f_high])

    assert res.status == "resolved"
    assert res.active_value == 19
    assert 18 in res.superseded_values
    assert "Policy 2" in res.resolution_rationale
