"""
Backfill vec_emb VECTOR ATTRIBUTE for all existing DocumentChunk vertices.

Reads existing 768-dim embeddings from DocumentChunk vertices and upserts them
into vec_emb to populate the native HNSW vector index with 0 LLM/embedding API calls.
"""

import logging
from src.graph.client import TigerGraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def backfill_chunk_vectors(batch_size: int = 500) -> None:
    client = TigerGraphClient()
    total_count = client.get_vertex_count("DocumentChunk")
    logger.info("Total DocumentChunk vertices in graph: %d", total_count)

    if total_count == 0:
        logger.info("No DocumentChunk vertices found to backfill.")
        return

    logger.info("Fetching all %d DocumentChunk vertices...", total_count)
    chunks = client.conn.getVertices("DocumentChunk", limit=total_count + 500)
    logger.info("Retrieved %d chunk records from Savanna.", len(chunks))

    batch_tuples = []
    total_backfilled = 0

    for ch in chunks:
        chunk_id = ch["v_id"]
        emb = ch.get("attributes", {}).get("embedding", [])
        if emb and len(emb) == 768:
            batch_tuples.append((chunk_id, {"vec_emb": emb}))

        if len(batch_tuples) >= batch_size:
            client.upsert_vertices("DocumentChunk", batch_tuples)
            total_backfilled += len(batch_tuples)
            logger.info("Backfilled %d/%d chunks with vec_emb.", total_backfilled, len(chunks))
            batch_tuples = []

    if batch_tuples:
        client.upsert_vertices("DocumentChunk", batch_tuples)
        total_backfilled += len(batch_tuples)

    logger.info("Backfill complete! Total chunks updated with vec_emb: %d", total_backfilled)


if __name__ == "__main__":
    backfill_chunk_vectors()
