"""
Conflict Detection for Olympic Claims.

Identifies discrepancies, value disagreements, and retroactive status changes
(e.g. doping disqualifications, medal reallocations, date reschedulings).
"""

from __future__ import annotations

import enum
import re
from typing import Optional
from pydantic import BaseModel, Field

from src.temporal.facts import Fact, FactStore


class ConflictType(str, enum.Enum):
    VALUE_DISAGREEMENT = "value_disagreement"
    STATUS_REVISION = "status_revision"
    TEMPORAL_OVERLAP = "temporal_overlap"
    UNCERTAINTY = "uncertainty"


class ConflictRecord(BaseModel):
    conflict_id: str
    conflict_type: ConflictType
    subject: str
    predicate: str
    fact_a: Fact
    fact_b: Fact
    description: str
    detected_markers: list[str] = Field(default_factory=list)


class ConflictDetector:
    """Scans and detects contradictions across retrieved factual assertions."""

    REVISION_REGEX = re.compile(
        r"\b(disqualified|stripped|reallocated|vacated|revised|postponed|doping|banned|retroactive)\b",
        re.IGNORECASE,
    )

    def detect_conflicts_for_claim(self, facts: list[Fact]) -> list[ConflictRecord]:
        """Compare all pairs of facts for a given subject-predicate claim."""
        conflicts = []
        n = len(facts)
        if n < 2:
            return conflicts

        for i in range(n):
            for j in range(i + 1, n):
                fa = facts[i]
                fb = facts[j]

                val_a = str(fa.value).strip().lower()
                val_b = str(fb.value).strip().lower()

                # If values agree, no conflict
                if val_a == val_b:
                    continue

                # Check for explicit status revision markers
                markers_a = self.REVISION_REGEX.findall(str(fa.revision_marker or "") + " " + str(fa.value))
                markers_b = self.REVISION_REGEX.findall(str(fb.revision_marker or "") + " " + str(fb.value))
                all_markers = list(set([m.lower() for m in markers_a + markers_b]))

                if all_markers:
                    c_type = ConflictType.STATUS_REVISION
                    desc = f"Status revision detected ({', '.join(all_markers)}) between '{fa.value}' and '{fb.value}'"
                else:
                    c_type = ConflictType.VALUE_DISAGREEMENT
                    desc = f"Direct value disagreement: '{fa.value}' vs '{fb.value}'"

                cid = f"conf-{fa.fact_id}-{fb.fact_id}"
                conf = ConflictRecord(
                    conflict_id=cid,
                    conflict_type=c_type,
                    subject=fa.subject,
                    predicate=fa.predicate,
                    fact_a=fa,
                    fact_b=fb,
                    description=desc,
                    detected_markers=all_markers,
                )
                conflicts.append(conf)

                # Link conflict IDs onto facts
                fa.conflict_ids.append(cid)
                fb.conflict_ids.append(cid)

        return conflicts

    def scan_store(self, store: FactStore) -> list[ConflictRecord]:
        all_conflicts = []
        for subject, predicate in store.all_claims():
            facts = store.get_facts_for_claim(subject, predicate)
            conflicts = self.detect_conflicts_for_claim(facts)
            all_conflicts.extend(conflicts)
        return all_conflicts
