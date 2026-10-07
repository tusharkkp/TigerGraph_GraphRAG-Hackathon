"""
Rebuild Event Layer Only in TigerGraph Savanna.

Deletes ONLY vertices of type 'Event' and their incident edges.
Leaves Document, DocumentChunk, Athlete, Country, Venue, Sport, and Games intact.
Re-upserts cleanly hashed Event vertices and edges, then re-links editions.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
from pathlib import Path

from src.graph.client import TigerGraphClient

# Import sibling scripts without relying on package structure
_scripts_dir = Path(__file__).resolve().parent

def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _scripts_dir / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_enrich_mod = _import_script("enrich_structured_corpus")
_link_mod = _import_script("link_edition_edges")
enrich_structured_corpus = _enrich_mod.enrich_structured_corpus
link_editions = _link_mod.link_editions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def rebuild_event_layer() -> None:
    tg = TigerGraphClient()
    
    logger.info("=" * 60)
    logger.info("PHASE 1: PRE-REBUILD GRAPH INVENTORY")
    logger.info("=" * 60)
    before_counts = {
        "Document": tg.get_vertex_count("Document"),
        "DocumentChunk": tg.get_vertex_count("DocumentChunk"),
        "Event": tg.get_vertex_count("Event"),
        "Athlete": tg.get_vertex_count("Athlete"),
        "Country": tg.get_vertex_count("Country"),
        "Venue": tg.get_vertex_count("Venue"),
        "Sport": tg.get_vertex_count("Sport"),
        "Games": tg.get_vertex_count("Games"),
        "DESCRIBES_EVENT": tg.get_edge_count("DESCRIBES_EVENT"),
        "PART_OF_GAMES": tg.get_edge_count("PART_OF_GAMES"),
        "HELD_AT": tg.get_edge_count("HELD_AT"),
        "BELONGS_TO_SPORT": tg.get_edge_count("BELONGS_TO_SPORT"),
        "MEDALIST": tg.get_edge_count("MEDALIST"),
        "PREVIOUS_EDITION": tg.get_edge_count("PREVIOUS_EDITION"),
        "NEXT_EDITION": tg.get_edge_count("NEXT_EDITION"),
    }
    for k, v in before_counts.items():
        logger.info("  %s: %s", k, v)

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2: PURGING EVENT VERTICES & INCIDENT EDGES")
    logger.info("=" * 60)
    logger.info("Executing delVerticesByType('Event')...")
    res = tg.conn.delVerticesByType("Event")
    logger.info("Delete result: %s", res)
    logger.info("Waiting for GPE engine to commit deletions...")
    for _ in range(10):
        time.sleep(3)
        cnt = tg.get_vertex_count("Event")
        logger.info("  Current Event count: %d", cnt)
        if cnt == 0:
            break

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3: RE-ENRICHING STRUCTURED CORPUS")
    logger.info("=" * 60)
    enrich_stats = enrich_structured_corpus()
    logger.info("Enrichment complete: %s", enrich_stats)

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 4: RE-LINKING EDITION EDGES")
    logger.info("=" * 60)
    link_editions()

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 5: POST-REBUILD VERIFICATION")
    logger.info("=" * 60)
    after_counts = {
        "Document": tg.get_vertex_count("Document"),
        "DocumentChunk": tg.get_vertex_count("DocumentChunk"),
        "Event": tg.get_vertex_count("Event"),
        "Athlete": tg.get_vertex_count("Athlete"),
        "Country": tg.get_vertex_count("Country"),
        "Venue": tg.get_vertex_count("Venue"),
        "Sport": tg.get_vertex_count("Sport"),
        "Games": tg.get_vertex_count("Games"),
        "DESCRIBES_EVENT": tg.get_edge_count("DESCRIBES_EVENT"),
        "PART_OF_GAMES": tg.get_edge_count("PART_OF_GAMES"),
        "HELD_AT": tg.get_edge_count("HELD_AT"),
        "BELONGS_TO_SPORT": tg.get_edge_count("BELONGS_TO_SPORT"),
        "MEDALIST": tg.get_edge_count("MEDALIST"),
        "PREVIOUS_EDITION": tg.get_edge_count("PREVIOUS_EDITION"),
        "NEXT_EDITION": tg.get_edge_count("NEXT_EDITION"),
    }
    for k, v in after_counts.items():
        diff = v - before_counts.get(k, 0)
        diff_str = f" ({'+' if diff > 0 else ''}{diff})" if diff != 0 else " (unchanged)"
        logger.info("  %s: %s%s", k, v, diff_str)


if __name__ == "__main__":
    rebuild_event_layer()
