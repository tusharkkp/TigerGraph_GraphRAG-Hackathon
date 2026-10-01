"""
High-level embedding helpers for document chunks and user queries.

Delegates all embedding operations to LLMGateway for caching,
rate limiting, token accounting, and retry behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import get_embedding_config
from src.contracts import EmbedResult

if TYPE_CHECKING:
    from src.llm.gateway import LLMGateway


class EmbeddingsService:
    """High-level service for generating text embeddings for ingestion and retrieval."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self._gateway = gateway
        self.config = get_embedding_config()
        self.doc_task = self.config.get("task_type", "RETRIEVAL_DOCUMENT")
        self.query_task = self.config.get("query_task_type", "RETRIEVAL_QUERY")

    @property
    def gateway(self) -> LLMGateway:
        """Lazily initialize default gateway if not provided."""
        if self._gateway is None:
            from src.llm.gateway import LLMGateway

            self._gateway = LLMGateway()
        return self._gateway

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        """Embed a list of document or chunk texts."""
        return self.gateway.embed(texts, task=self.doc_task)

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for vector search."""
        res = self.gateway.embed([query], task=self.query_task)
        if not res.embeddings:
            raise ValueError(f"No embedding returned for query: {query[:50]}...")
        return res.embeddings[0]
