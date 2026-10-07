"""
Compute and upsert PREVIOUS_EDITION and NEXT_EDITION edges between Event vertices.

Links consecutive Olympic editions of the same sport event (e.g. 2012 -> 2008).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from src.config import PROJECT_ROOT
from src.graph.client import TigerGraphClient
from src.ingestion.structured_parser import StructuredInfoboxParser, build_match_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def link_editions() -> None:
    corpus_path = PROJECT_ROOT / "Dataset" / "corpus" / "corpus.jsonl"
    events = []

    logger.info("Parsing all events from corpus...")
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            p = StructuredInfoboxParser.parse_document(doc)
            if p and p.event_id and p.year:
                events.append(p)

    logger.info("Parsed %d events.", len(events))

    # Group events by normalized series key
    by_series: dict[str, dict[int, str]] = defaultdict(dict)
    for p in events:
        key = build_match_key(f"{p.sport} {p.event_name}")
        by_series[key][p.year] = p.event_id

    prev_edges = []
    next_edges = []

    for p in events:
        key = build_match_key(f"{p.sport} {p.event_name}")
        series = by_series[key]
        if p.prev_year and p.prev_year in series:
            target_id = series[p.prev_year]
            prev_edges.append(("Event", p.event_id, "PREVIOUS_EDITION", "Event", target_id, {}))
        if p.next_year and p.next_year in series:
            target_id = series[p.next_year]
            next_edges.append(("Event", p.event_id, "NEXT_EDITION", "Event", target_id, {}))

    logger.info("Computed %d PREVIOUS_EDITION edges and %d NEXT_EDITION edges.", len(prev_edges), len(next_edges))

    tg = TigerGraphClient()
    if prev_edges:
        tg.upsert_edges(prev_edges)
        logger.info("Successfully upserted %d PREVIOUS_EDITION edges into Savanna.", len(prev_edges))
    if next_edges:
        tg.upsert_edges(next_edges)
        logger.info("Successfully upserted %d NEXT_EDITION edges into Savanna.", len(next_edges))


if __name__ == "__main__":
    link_editions()
