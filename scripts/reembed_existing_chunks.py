"""
Re-embed previously ingested DocumentChunks in TigerGraph using the local BGE model (ADR-007).

Idempotently updates vec_emb and embedding attributes on DocumentChunk vertices,
ensuring a unified 768-dim embedding space across the graph.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.config import PROJECT_ROOT
from src.graph.client import TigerGraphClient
from src.ingestion.chunker import TextChunker
from src.llm.embeddings import EmbeddingsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def reembed_existing_chunks() -> None:
    ckpt_path = PROJECT_ROOT / "data" / "processed" / "ingestion_checkpoint.json"
    corpus_path = PROJECT_ROOT / "Dataset" / "corpus" / "corpus.jsonl"

    if not ckpt_path.exists():
        logger.error("Checkpoint file not found: %s", ckpt_path)
        return

    with open(ckpt_path, encoding="utf-8") as f:
        data = json.load(f)
    processed_doc_ids = set(data.get("processed_docs", []))
    # Also include Q213208 (doc 56 that was partially upserted)
    processed_doc_ids.add("Q213208")

    logger.info("Found %d docs to re-embed.", len(processed_doc_ids))

    chunker = TextChunker()
    embeddings_service = EmbeddingsService()
    tg_client = TigerGraphClient()

    logger.info("Using embedding model: %s (dim=%d)", embeddings_service.model_name, embeddings_service.dimensions)

    all_chunks_to_update: list[dict] = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            did = str(doc.get("doc_id", ""))
            if did in processed_doc_ids:
                chunks = chunker.chunk_document(doc)
                all_chunks_to_update.extend(chunks)

    logger.info("Generated %d chunks across %d docs for re-embedding.", len(all_chunks_to_update), len(processed_doc_ids))

    # Batch embedding in chunks of 64
    batch_size = 64
    total_chunks = len(all_chunks_to_update)
    t0 = time.perf_counter()

    for i in range(0, total_chunks, batch_size):
        batch = all_chunks_to_update[i : i + batch_size]
        texts = [c["text"] for c in batch]
        res = embeddings_service.embed_documents(texts)

        # Build TigerGraph upsert tuples
        tg_tuples = []
        for j, c in enumerate(batch):
            emb = res.embeddings[j]
            tg_tuples.append((
                c["chunk_id"],
                {
                    "chunk_index": c["chunk_index"],
                    "text": c["text"],
                    "approx_tokens": c["approx_tokens"],
                    "embedding": emb,
                    "vec_emb": emb,
                }
            ))

        tg_client.upsert_vertices("DocumentChunk", tg_tuples)
        logger.info("Re-embedded and upserted [%d/%d] chunks.", min(i + batch_size, total_chunks), total_chunks)

    elapsed = time.perf_counter() - t0
    logger.info("Successfully re-embedded %d chunks in %.2f seconds (%.1f chunks/sec).", total_chunks, elapsed, total_chunks / max(elapsed, 0.001))


if __name__ == "__main__":
    reembed_existing_chunks()
