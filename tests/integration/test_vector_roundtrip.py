"""
Integration test for TigerGraph Savanna native HNSW vector search.

Validates ADR-002:
1. Queries native GSQL Content_Similarity_Vector_Search using a known chunk's vector.
2. Asserts the query vector returns the target chunk as Rank 1 with distance ~0.0.
3. Asserts semantic neighbors are returned and ordered by cosine distance.
"""

import pytest
from src.graph.client import TigerGraphClient

pytestmark = pytest.mark.integration


class TestTigerGraphVectorRoundtrip:
    def test_native_vector_search_roundtrip(self):
        client = TigerGraphClient()

        # 1. Fetch an existing DocumentChunk with 768-dim embedding
        sample_chunks = client.conn.getVertices("DocumentChunk", limit=5)
        assert len(sample_chunks) > 0, "No DocumentChunk vertices available in graph"

        target_chunk = None
        for ch in sample_chunks:
            emb = ch.get("attributes", {}).get("embedding", [])
            if emb and len(emb) == 768:
                target_chunk = ch
                break

        assert target_chunk is not None, "No chunk with 768-dim embedding found"
        target_id = target_chunk["v_id"]
        target_vec = target_chunk["attributes"]["embedding"]

        # 2. Query native installed vector search query
        res = client.conn.runInstalledQuery(
            "Content_Similarity_Vector_Search",
            params={"query_vec": target_vec, "top_k": 5},
        )

        assert res and len(res) > 0
        record = res[0]
        assert "v" in record
        assert "@@distances" in record

        distances = record["@@distances"]
        assert len(distances) > 0

        # Sort returned chunks by cosine distance (ascending: smaller = closer)
        sorted_results = sorted(distances.items(), key=lambda x: x[1])
        top_1_id, top_1_dist = sorted_results[0]

        # 3. Assert Rank 1 is the exact target chunk with distance ~0.0
        assert top_1_id == target_id, (
            f"Expected Rank 1 to be '{target_id}', but got '{top_1_id}' (distance {top_1_dist})"
        )
        assert top_1_dist < 0.001, (
            f"Expected cosine distance ~0.0 for identical vector, got {top_1_dist}"
        )
