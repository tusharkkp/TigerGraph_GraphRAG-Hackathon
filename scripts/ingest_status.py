"""
Status monitor for full corpus ingestion.

Reports current progress, throughput (docs/sec, chunks/sec), elapsed time,
ETA, and live TigerGraph Savanna counts.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
import time
from pathlib import Path

from src.config import PROJECT_ROOT, REPORTS_DIR
from src.graph.client import TigerGraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = PROJECT_ROOT / "data" / "processed" / "ingestion_checkpoint.json"
STATUS_FILE = REPORTS_DIR / "ingestion_status.json"
TOTAL_CORPUS_DOCS = 2951


def get_status() -> dict:
    processed_docs = set()
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
                data = json.load(f)
                processed_docs = set(data.get("processed_docs", []))
        except Exception as e:
            logger.warning("Error reading checkpoint: %s", e)

    docs_done = len(processed_docs)
    pct_done = (docs_done / TOTAL_CORPUS_DOCS) * 100

    # Read status file if available for rates
    rate_info = {}
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                rate_info = json.load(f)
        except Exception:
            pass

    # Fetch live Savanna counts
    tg_counts = {}
    try:
        tg = TigerGraphClient()
        tg_counts["Document"] = tg.conn.getVertexCount("Document")
        tg_counts["DocumentChunk"] = tg.conn.getVertexCount("DocumentChunk")
        tg_counts["Event"] = tg.conn.getVertexCount("Event")
        tg_counts["Athlete"] = tg.conn.getVertexCount("Athlete")
    except Exception as e:
        tg_counts["error"] = str(e)

    status = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "total_docs": TOTAL_CORPUS_DOCS,
        "processed_docs": docs_done,
        "remaining_docs": TOTAL_CORPUS_DOCS - docs_done,
        "progress_percent": round(pct_done, 2),
        "docs_per_sec": rate_info.get("docs_per_sec", 0.0),
        "chunks_per_sec": rate_info.get("chunks_per_sec", 0.0),
        "elapsed_seconds": rate_info.get("elapsed_seconds", 0.0),
        "eta_seconds": rate_info.get("eta_seconds", 0.0),
        "eta_human": rate_info.get("eta_human", "Calculating..."),
        "savanna_counts": tg_counts,
    }
    return status


def main() -> None:
    status = get_status()
    print("=" * 60)
    print("          INGESTION STATUS MONITOR")
    print("=" * 60)
    print(f"Progress:       {status['processed_docs']} / {status['total_docs']} docs ({status['progress_percent']}%)")
    print(f"Remaining:      {status['remaining_docs']} docs")
    print(f"Throughput:     {status['docs_per_sec']:.2f} docs/sec | {status['chunks_per_sec']:.2f} chunks/sec")
    print(f"Elapsed:        {status['elapsed_seconds']:.1f}s")
    print(f"ETA:            {status['eta_human']}")
    print("-" * 60)
    print("Savanna Graph Counts:")
    for k, v in status["savanna_counts"].items():
        print(f"  - {k}: {v}")
    print("=" * 60)


if __name__ == "__main__":
    main()
