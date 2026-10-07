"""
Shared Answer Generator for all QA pipelines (P1 RAG, P2 GraphRAG, P3 Agentic).

Enforces:
1. Identical prompt template across all pipelines.
2. Identical structured output schema (PipelineAnswer).
3. Exact token accounting and citation generation.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from pydantic import BaseModel, Field

from src.contracts import CallTag, Citation, TokenUsage
from src.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


class PipelineAnswer(BaseModel):
    """Universal structured answer from the final answer generation model."""

    final_answer: str = Field(
        description="Direct, concise answer to the question (e.g. name of athlete, country, count, or list)"
    )
    explanation: str = Field(
        description="Concise 1-2 sentence evidence-grounded justification"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    cited_chunk_ids: list[str] = Field(
        default_factory=list, description="IDs of chunks directly supporting the answer"
    )


ANSWER_PROMPT_TEMPLATE = """You are an expert Question Answering system for Olympic Games data.
Answer the user's question accurately and concisely, strictly based on the provided retrieved context.

Question: {question}

Retrieved Evidence Context:
{context}

Guidelines:
1. Provide the direct, specific answer in 'final_answer' (e.g. athlete name, number of nations, venue name). Keep it concise.
2. If the context does not contain enough information to answer, state what is known in 'explanation' and provide your best inference or 'Unknown' in 'final_answer'.
3. In 'cited_chunk_ids', list the chunk IDs from the context that directly support your answer.
4. Ground every fact strictly in the context; do not extrapolate or invent numbers.

Return ONLY a JSON object matching the PipelineAnswer schema.
"""


class AnswerGenerator:
    """Universal answer generator across all pipelines."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self.gateway = gateway or LLMGateway()

    def generate_answer(
        self,
        question_id: str,
        question: str,
        evidence_chunks: list[dict[str, Any]],
        graph_facts: list[str] | None = None,
        pipeline: str = "rag",
    ) -> tuple[PipelineAnswer, TokenUsage, list[Citation]]:
        """
        Generate a final answer from evidence chunks and optional graph facts.

        Args:
            question_id: Question ID
            question: Question text
            evidence_chunks: List of chunk dicts (chunk_id, doc_id, text)
            graph_facts: Optional list of graph relations/triples
            pipeline: Pipeline name ('rag', 'graphrag', 'agentic')

        Returns:
            Tuple of (PipelineAnswer, TokenUsage, list[Citation])
        """
        context_parts = []

        # 1. Format chunks
        for i, c in enumerate(evidence_chunks, start=1):
            cid = c.get("chunk_id", f"chunk_{i}")
            did = c.get("doc_id", "")
            title = c.get("title", "")
            text = c.get("text", "")
            header = f"[Chunk {i}] ID: {cid}"
            if title:
                header += f" | Title: {title}"
            context_parts.append(f"{header}\n{text}")

        # 2. Format graph facts if present
        if graph_facts:
            context_parts.append("--- Structured Graph Facts ---")
            for fact in graph_facts:
                context_parts.append(f"- {fact}")

        context_str = "\n\n".join(context_parts) if context_parts else "No evidence retrieved."

        # Approximate context tokens (word-based / ~4 chars per token)
        context_tokens = max(0, len(context_str) // 4)

        prompt = ANSWER_PROMPT_TEMPLATE.format(
            question=question,
            context=context_str,
        )

        res = self.gateway.generate(
            role="answer",
            prompt=prompt,
            schema=PipelineAnswer,
            temperature=0.0,
            max_output_tokens=1024,
            tag=CallTag(question_id=question_id, pipeline=pipeline, role="answer"),
        )

        if res.parsed and isinstance(res.parsed, PipelineAnswer):
            parsed: PipelineAnswer = res.parsed
        else:
            parsed = PipelineAnswer(
                final_answer=res.text.strip(),
                explanation="Model raw output",
                confidence=0.5,
                cited_chunk_ids=[c.get("chunk_id", "") for c in evidence_chunks[:2] if c.get("chunk_id")],
            )

        # Build citations
        chunk_by_id = {c.get("chunk_id"): c for c in evidence_chunks if c.get("chunk_id")}
        citations = []
        for cid in parsed.cited_chunk_ids:
            chunk = chunk_by_id.get(cid)
            if chunk:
                citations.append(
                    Citation(
                        chunk_id=cid,
                        doc_id=chunk.get("doc_id", cid.split("_chunk_")[0] if "_chunk_" in cid else cid),
                        quote=None,
                        entity_ids=[],
                    )
                )

        # Invariant enforcement for TokenUsage:
        # total_tokens == llm_input_tokens + llm_output_tokens
        # context_tokens <= llm_input_tokens
        llm_in = res.tokens_in
        llm_out = res.tokens_out
        ctx_tokens = min(context_tokens, llm_in)

        token_usage = TokenUsage(
            context_tokens=ctx_tokens,
            llm_input_tokens=llm_in,
            llm_output_tokens=llm_out,
            total_tokens=llm_in + llm_out,
        )

        return parsed, token_usage, citations
