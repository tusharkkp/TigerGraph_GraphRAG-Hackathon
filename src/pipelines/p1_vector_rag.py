"""
Pipeline 1: Standard Vector RAG Baseline.

Workflow:
1. Embed input question via EmbeddingsService (task_type=RETRIEVAL_QUERY).
2. Query native TigerGraph Savanna HNSW index via Content_Similarity_Vector_Search.
3. Rank chunks by ascending distance (1 - cosine).
4. Generate final answer via shared AnswerGenerator.
5. Return universal PipelineResult with TokenUsage, citations, and retrieved chunk IDs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.contracts import Citation, PipelineResult, Question, TokenUsage
from src.graph.client import TigerGraphClient
from src.llm.embeddings import EmbeddingsService
from src.llm.gateway import LLMGateway
from src.pipelines.answer_generator import AnswerGenerator, PipelineAnswer

logger = logging.getLogger(__name__)


class VectorRAGPipeline:
    """Standard Vector RAG pipeline using TigerGraph native HNSW vector index."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        tg_client: TigerGraphClient | None = None,
        embeddings_service: EmbeddingsService | None = None,
        answer_generator: AnswerGenerator | None = None,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.tg_client = tg_client or TigerGraphClient()
        self.embeddings = embeddings_service or EmbeddingsService(gateway=self.gateway)
        self.answer_generator = answer_generator or AnswerGenerator(gateway=self.gateway)

    def retrieve_chunks(self, question_text: str, top_k: int = 5) -> tuple[list[dict[str, Any]], str]:
        """
        Embed question and query TigerGraph native HNSW index.
        Returns:
            Tuple of (ranked_chunks, retrieval_backend_tag)
        """
        # 1. Embed query
        raw_vec = self.embeddings.embed_query(question_text)
        query_vec = [float(x) for x in raw_vec] if raw_vec else []

        if not query_vec:
            logger.warning("Empty query embedding generated for: %s", question_text)
            return [], "empty_embedding"

        # 2. Native HNSW vector search on TigerGraph Savanna
        try:
            query_res = self.tg_client.run_query(
                "Content_Similarity_Vector_Search",
                params={"query_vec": query_vec, "top_k": top_k},
            )
            backend_tag = "native_hnsw"
        except Exception as e:
            logger.error("Native vector search failed, falling back: %s", e)
            return [], f"error_{str(e)[:50]}"

        if not query_res or not isinstance(query_res, list):
            return [], backend_tag

        record = query_res[0]
        distances: dict[str, float] = record.get("@@distances", {})
        vertices: list[dict[str, Any]] = record.get("v", [])

        # Build vertex attribute map
        v_attrs: dict[str, dict[str, Any]] = {}
        for v in vertices:
            vid = v.get("v_id")
            attrs = v.get("attributes", {})
            if vid:
                v_attrs[vid] = {
                    "chunk_id": vid,
                    "chunk_index": attrs.get("v.chunk_index", 0),
                    "text": attrs.get("v.text", ""),
                    "approx_tokens": attrs.get("v.approx_tokens", 0),
                    "doc_id": vid.rsplit("_c", 1)[0] if "_c" in vid else (vid.rsplit("_chunk_", 1)[0] if "_chunk_" in vid else vid),
                }

        # Sort by distance ascending (1 - cosine)
        sorted_pairs = sorted(distances.items(), key=lambda x: x[1])
        ranked_chunks = []
        for vid, dist in sorted_pairs[:top_k]:
            if vid in v_attrs:
                chunk_data = dict(v_attrs[vid])
                chunk_data["distance"] = dist
                ranked_chunks.append(chunk_data)

        return ranked_chunks, backend_tag

    def run(self, question: Question | dict[str, Any], top_k: int = 5) -> PipelineResult:
        """
        Execute Vector RAG pipeline for a question.
        """
        start_time = time.perf_counter()

        if isinstance(question, Question):
            qid = question.qid
            qtext = question.question
        else:
            qid = question["qid"]
            qtext = question["question"]

        logger.info("[P1 Vector RAG] Running for %s: %s", qid, qtext)

        # 1. Retrieve chunks
        evidence_chunks, backend_tag = self.retrieve_chunks(qtext, top_k=top_k)
        retrieved_chunk_ids = [c["chunk_id"] for c in evidence_chunks]

        # 2. Generate answer
        answer_obj, token_usage, citations = self.answer_generator.generate_answer(
            question_id=qid,
            question=qtext,
            evidence_chunks=evidence_chunks,
            pipeline="rag",
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return PipelineResult(
            question_id=qid,
            pipeline="rag",
            answer=answer_obj.final_answer,
            citations=citations,
            retrieved_chunk_ids=retrieved_chunk_ids,
            tokens=token_usage,
            latency_ms=latency_ms,
            trace=[],
            stop_reason=None,
            strategy_changed=False,
            error=None,
        )


if __name__ == "__main__":
    pipeline = VectorRAGPipeline()
    sample_q = {
        "qid": "pub-002",
        "question": "Who won the men's 20 km walk at the 2012 Summer Olympics?",
    }
    result = pipeline.run(sample_q, top_k=3)
    print("\nResult:")
    print(result.model_dump_json(indent=2))
