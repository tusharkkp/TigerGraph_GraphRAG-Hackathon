"""
Pipeline 2: GraphRAG Baseline.

Workflow:
1. Embed input question via EmbeddingsService (task_type=RETRIEVAL_QUERY).
2. Query native TigerGraph Savanna HNSW index via Content_Similarity_Vector_Search.
3. Perform 1-hop graph expansion from retrieved documents/entities:
   - Document -> DESCRIBES_EVENT -> Event
   - Event -> MEDALIST -> Athlete (with medal, noc)
   - Event -> HELD_AT -> Venue
   - Event -> BELONGS_TO_SPORT -> Sport
   - Event -> PART_OF_GAMES -> Games
   (Strictly non-agentic: deterministic 1-hop neighborhood traversal, no dynamic loops).
4. Combine chunk evidence and structured graph facts into prompt context.
5. Generate final answer via shared AnswerGenerator.
6. Return universal PipelineResult with TokenUsage, citations, and retrieved chunk IDs.
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


class GraphRAGPipeline:
    """GraphRAG pipeline combining native vector search with 1-hop graph traversal."""

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
        """
        raw_vec = self.embeddings.embed_query(question_text)
        query_vec = [float(x) for x in raw_vec] if raw_vec else []
        if not query_vec:
            return [], "empty_embedding"

        try:
            query_res = self.tg_client.run_query(
                "Content_Similarity_Vector_Search",
                params={"query_vec": query_vec, "top_k": top_k},
            )
            backend_tag = "native_hnsw"
        except Exception as e:
            logger.error("Native vector search failed in GraphRAG: %s", e)
            return [], f"error_{str(e)[:50]}"

        if not query_res or not isinstance(query_res, list):
            return [], backend_tag

        record = query_res[0]
        distances: dict[str, float] = record.get("@@distances", {})
        vertices: list[dict[str, Any]] = record.get("v", [])

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

        sorted_pairs = sorted(distances.items(), key=lambda x: x[1])
        ranked_chunks = []
        for vid, dist in sorted_pairs[:top_k]:
            if vid in v_attrs:
                chunk_data = dict(v_attrs[vid])
                chunk_data["distance"] = dist
                ranked_chunks.append(chunk_data)

        return ranked_chunks, backend_tag

    def expand_1hop_graph(self, doc_ids: list[str]) -> list[str]:
        """
        Perform 1-hop graph expansion for the given doc_ids via installed GSQL query Get_Event_Context.
        Retrieves Event, Medalists, Venues, Sports, and Games in a single fast call (<300ms).
        """
        if not doc_ids:
            return []

        graph_facts: list[str] = []
        try:
            res = self.tg_client.conn.runInstalledQuery("Get_Event_Context", params={"doc_ids": doc_ids})
        except Exception as e:
            logger.debug("Get_Event_Context installed query failed: %s", e)
            return []

        events_map: dict[str, dict] = {}
        medalist_names: list[str] = []
        venue_names: list[str] = []
        sport_names: list[str] = []
        games_info: list[str] = []

        for record in res:
            if "Events" in record:
                for ev in record["Events"]:
                    eid = ev.get("v_id")
                    attrs = ev.get("attributes", {})
                    events_map[eid] = {
                        "name": attrs.get("Events.name", eid),
                        "year": attrs.get("Events.year"),
                        "season": attrs.get("Events.season"),
                        "gender": attrs.get("Events.gender"),
                        "competitors": attrs.get("Events.competitors"),
                        "nations": attrs.get("Events.nations"),
                        "winning_value": attrs.get("Events.winning_value"),
                    }
            if "Medalists" in record:
                for a in record["Medalists"]:
                    attrs = a.get("attributes", {})
                    name = attrs.get("Medalists.name")
                    if name and name not in medalist_names:
                        medalist_names.append(name)
            if "Venues" in record:
                for v in record["Venues"]:
                    attrs = v.get("attributes", {})
                    name = attrs.get("Venues.name")
                    if name and name not in venue_names:
                        venue_names.append(name)
            if "Sports" in record:
                for s in record["Sports"]:
                    attrs = s.get("attributes", {})
                    name = attrs.get("Sports.name")
                    if name and name not in sport_names:
                        sport_names.append(name)
            if "GamesV" in record:
                for g in record["GamesV"]:
                    attrs = g.get("attributes", {})
                    yr = attrs.get("GamesV.year")
                    sn = attrs.get("GamesV.season")
                    if yr and sn:
                        games_info.append(f"{yr} {sn} Olympics")

        for eid, ev in events_map.items():
            fact = f"Event: {ev['name']}"
            if ev.get("year"):
                fact += f" ({ev['year']})"
            if ev.get("nations"):
                fact += f" | Participating Nations: {ev['nations']}"
            if ev.get("competitors"):
                fact += f" | Competitors: {ev['competitors']}"
            if ev.get("winning_value"):
                fact += f" | Winning Mark/Time: {ev['winning_value']}"
            graph_facts.append(fact)

        if medalist_names:
            graph_facts.append(f"Medalists: {', '.join(medalist_names)}")
        if venue_names:
            graph_facts.append(f"Venue(s): {', '.join(venue_names)}")
        if sport_names:
            graph_facts.append(f"Sport: {', '.join(sport_names)}")
        if games_info:
            graph_facts.append(f"Games: {', '.join(set(games_info))}")

        return graph_facts

    def run(self, question: Question | dict[str, Any], top_k: int = 5) -> PipelineResult:
        """
        Execute GraphRAG pipeline for a question.
        """
        start_time = time.perf_counter()

        if isinstance(question, Question):
            qid = question.qid
            qtext = question.question
        else:
            qid = question["qid"]
            qtext = question["question"]

        logger.info("[P2 GraphRAG] Running for %s: %s", qid, qtext)

        # 1. Retrieve chunks via vector search
        evidence_chunks, backend_tag = self.retrieve_chunks(qtext, top_k=top_k)
        retrieved_chunk_ids = [c["chunk_id"] for c in evidence_chunks]

        # 2. Extract doc_ids for 1-hop graph expansion
        doc_ids = list(dict.fromkeys([c["doc_id"] for c in evidence_chunks if c.get("doc_id")]))

        # 3. 1-hop graph expansion
        graph_facts = self.expand_1hop_graph(doc_ids)

        # 4. Generate answer with chunks + graph facts
        answer_obj, token_usage, citations = self.answer_generator.generate_answer(
            question_id=qid,
            question=qtext,
            evidence_chunks=evidence_chunks,
            graph_facts=graph_facts,
            pipeline="graphrag",
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return PipelineResult(
            question_id=qid,
            pipeline="graphrag",
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
    pipeline = GraphRAGPipeline()
    sample_q = {
        "qid": "pub-002",
        "question": "Who won the men's 20 km walk at the 2012 Summer Olympics?",
    }
    result = pipeline.run(sample_q, top_k=3)
    print("\nGraphRAG Result:")
    print(result.model_dump_json(indent=2))
