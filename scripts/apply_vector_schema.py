"""Apply native HNSW vector attribute and install Content_Similarity_Vector_Search query."""

import logging
from src.graph.client import TigerGraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def apply_vector_schema() -> None:
    client = TigerGraphClient()
    gname = client.settings.tg_graphname or "GraphRAG"

    logger.info("Applying schema change job to add vec_emb to DocumentChunk on graph %s...", gname)
    schema_job = f"""
USE GRAPH {gname}
DROP JOB add_vec_emb
CREATE SCHEMA_CHANGE JOB add_vec_emb FOR GRAPH {gname} {{
  ALTER VERTEX DocumentChunk ADD VECTOR ATTRIBUTE vec_emb(DIMENSION=768, METRIC="COSINE");
}}
RUN SCHEMA_CHANGE JOB add_vec_emb
DROP JOB add_vec_emb
"""
    res = client.conn.gsql(schema_job)
    logger.info("Schema change response:\n%s", res)

    logger.info("Installing Content_Similarity_Vector_Search query...")
    query_gsql = f"""
USE GRAPH {gname}
CREATE OR REPLACE QUERY Content_Similarity_Vector_Search(LIST<FLOAT> query_vec, INT top_k = 10) FOR GRAPH {gname} SYNTAX v3 {{
  MapAccum<VERTEX<DocumentChunk>, FLOAT> @@distances;
  
  v = vectorSearch({{DocumentChunk.vec_emb}}, query_vec, top_k, {{ distance_map: @@distances }});
  
  PRINT v[v.chunk_index, v.text, v.approx_tokens], @@distances;
}}
INSTALL QUERY Content_Similarity_Vector_Search
"""
    q_res = client.conn.gsql(query_gsql)
    logger.info("Query install response:\n%s", q_res)

    status = client.conn.getVectorStatus("DocumentChunk")
    logger.info("DocumentChunk vector status ready: %s", status)


if __name__ == "__main__":
    apply_vector_schema()
