"""
Batch-enrich TigerGraph Savanna with deterministic structured entities and relations.

Extracts all Olympic Events, Games, Athletes, Countries, Venues, Sports,
and edges (MEDALIST, HELD_AT, PART_OF_GAMES, BELONGS_TO_SPORT, REPRESENTS, DESCRIBES_EVENT)
from the corpus without any LLM calls (100% deterministic and instantaneous).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.graph.client import TigerGraphClient
from src.ingestion.structured_parser import StructuredInfoboxParser
from src.utils.normalization import clean_text_for_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CORPUS_PATH = Path("Dataset/corpus/corpus.jsonl")
BATCH_SIZE_VERTICES = 200
BATCH_SIZE_EDGES = 500


def enrich_structured_corpus() -> dict[str, int]:
    client = TigerGraphClient()
    logger.info("Starting structured graph enrichment from %s...", CORPUS_PATH)

    # 1. Collect all elements
    docs_to_upsert: dict[str, dict[str, Any]] = {}
    events_to_upsert: dict[str, dict[str, Any]] = {}
    games_to_upsert: dict[str, dict[str, Any]] = {}
    athletes_to_upsert: dict[str, dict[str, Any]] = {}
    countries_to_upsert: dict[str, dict[str, Any]] = {}
    venues_to_upsert: dict[str, dict[str, Any]] = {}
    sports_to_upsert: dict[str, dict[str, Any]] = {}
    all_edges: list[tuple[str, str, str, str, str, dict[str, Any]]] = []

    infobox_count = 0
    total_docs = 0

    with open(CORPUS_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total_docs += 1
            doc = json.loads(line)
            doc_id = doc["doc_id"]

            # Store clean document vertex
            docs_to_upsert[doc_id] = {
                "title": clean_text_for_storage(doc.get("title", "")),
                "url": doc.get("url", ""),
                "wikidata_qid": doc.get("wikidata_qid", ""),
                "approx_tokens": doc.get("approx_tokens", 0),
            }

            parsed = StructuredInfoboxParser.parse_document(doc)
            if parsed:
                infobox_count += 1
                elements = StructuredInfoboxParser.build_graph_elements(parsed)

                for vid, attrs in elements["Event"]:
                    events_to_upsert[vid] = attrs
                for vid, attrs in elements["Games"]:
                    games_to_upsert[vid] = attrs
                for vid, attrs in elements["Athlete"]:
                    athletes_to_upsert[vid] = attrs
                for vid, attrs in elements["Country"]:
                    countries_to_upsert[vid] = attrs
                for vid, attrs in elements["Venue"]:
                    venues_to_upsert[vid] = attrs
                for vid, attrs in elements["Sport"]:
                    sports_to_upsert[vid] = attrs

                all_edges.extend(elements["edges"])

    logger.info("Parsing complete: %d/%d documents have Olympic infoboxes.", infobox_count, total_docs)
    logger.info(
        "Extracted: %d Events, %d Athletes, %d Countries, %d Venues, %d Sports, %d Games, %d Edges.",
        len(events_to_upsert),
        len(athletes_to_upsert),
        len(countries_to_upsert),
        len(venues_to_upsert),
        len(sports_to_upsert),
        len(games_to_upsert),
        len(all_edges),
    )

    # 2. Batch-upsert vertices
    vertex_groups = [
        ("Document", list(docs_to_upsert.items())),
        ("Event", list(events_to_upsert.items())),
        ("Games", list(games_to_upsert.items())),
        ("Athlete", list(athletes_to_upsert.items())),
        ("Country", list(countries_to_upsert.items())),
        ("Venue", list(venues_to_upsert.items())),
        ("Sport", list(sports_to_upsert.items())),
    ]

    total_vertices_upserted = 0
    for vtype, items in vertex_groups:
        logger.info("Upserting %d vertices of type '%s' in batches of %d...", len(items), vtype, BATCH_SIZE_VERTICES)
        for i in range(0, len(items), BATCH_SIZE_VERTICES):
            batch = items[i : i + BATCH_SIZE_VERTICES]
            res = client.upsert_vertices(vtype, batch)
            total_vertices_upserted += res

    # 3. Batch-upsert edges
    # Deduplicate edges by (source_type, source_id, edge_type, target_type, target_id)
    deduped_edges: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for st, sid, et, tt, tid, attrs in all_edges:
        key = (st, sid, et, tt, tid)
        deduped_edges[key] = attrs

    edge_items = [
        (st, sid, et, tt, tid, attrs)
        for (st, sid, et, tt, tid), attrs in deduped_edges.items()
    ]

    logger.info("Upserting %d unique edges in batches of %d...", len(edge_items), BATCH_SIZE_EDGES)
    total_edges_upserted = 0
    for i in range(0, len(edge_items), BATCH_SIZE_EDGES):
        batch = edge_items[i : i + BATCH_SIZE_EDGES]
        res = client.upsert_edges(batch)
        total_edges_upserted += res

    # 4. Verify graph counts
    logger.info("=== Graph Enrichment Summary ===")
    counts = {
        "Document": client.get_vertex_count("Document"),
        "Event": client.get_vertex_count("Event"),
        "Games": client.get_vertex_count("Games"),
        "Athlete": client.get_vertex_count("Athlete"),
        "Country": client.get_vertex_count("Country"),
        "Venue": client.get_vertex_count("Venue"),
        "Sport": client.get_vertex_count("Sport"),
        "MEDALIST": client.get_edge_count("MEDALIST"),
        "HELD_AT": client.get_edge_count("HELD_AT"),
        "PART_OF_GAMES": client.get_edge_count("PART_OF_GAMES"),
        "BELONGS_TO_SPORT": client.get_edge_count("BELONGS_TO_SPORT"),
        "REPRESENTS": client.get_edge_count("REPRESENTS"),
        "DESCRIBES_EVENT": client.get_edge_count("DESCRIBES_EVENT"),
    }
    for name, cnt in counts.items():
        logger.info("  %s count in TigerGraph: %d", name, cnt)

    return counts


if __name__ == "__main__":
    enrich_structured_corpus()
