"""
High-level embedding helpers for document chunks and user queries.

Provides an EmbeddingProvider abstraction with FastEmbedProvider (local default)
and GeminiEmbeddingProvider (optional remote), handling model prefixes, dimension
verification, and token accounting.
"""

from __future__ import annotations

import abc
import time
from typing import TYPE_CHECKING, Any

from src.config import get_embedding_config
from src.contracts import EmbedResult

if TYPE_CHECKING:
    from src.llm.gateway import LLMGateway


class EmbeddingProvider(abc.ABC):
    """Abstract base class for embedding providers."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """The identifier of the underlying embedding model."""
        ...

    @property
    @abc.abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality."""
        ...

    @abc.abstractmethod
    def embed_documents(self, texts: list[str]) -> EmbedResult:
        """Embed a list of document or chunk texts."""
        ...

    @abc.abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for vector search."""
        ...


class FastEmbedProvider(EmbeddingProvider):
    """Local CPU-friendly embedding provider using FastEmbed (ONNX runtime)."""

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int | None = None,
        query_prefix: str | None = None,
        doc_prefix: str | None = None,
        batch_size: int = 32,
        threads: int | None = None,
    ) -> None:
        cfg = get_embedding_config()
        self._model_name = model_name or cfg.get("model", "BAAI/bge-base-en-v1.5")
        self._dimensions = dimensions or int(cfg.get("dimensions", 768))
        self.query_prefix = query_prefix if query_prefix is not None else cfg.get(
            "query_prefix", "Represent this sentence for searching relevant passages: "
        )
        self.doc_prefix = doc_prefix if doc_prefix is not None else cfg.get("doc_prefix", "")
        self.batch_size = batch_size or int(cfg.get("batch_size", 32))
        self._threads = threads
        self._model: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            kwargs: dict[str, Any] = {"model_name": self._model_name}
            if self._threads is not None:
                kwargs["threads"] = self._threads
            self._model = TextEmbedding(**kwargs)
        return self._model

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        if not texts:
            return EmbedResult(
                embeddings=[],
                dimensions=self.dimensions,
                tokens_used=0,
                latency_ms=0,
                model=self.model_name,
            )

        t0 = time.perf_counter()
        prefixed_texts = [self.doc_prefix + t for t in texts] if self.doc_prefix else texts
        model = self._get_model()
        embs_gen = model.embed(prefixed_texts, batch_size=self.batch_size)
        embeddings = [list(e) for e in embs_gen]
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Approximate tokens used
        approx_tokens = sum(max(1, len(t) // 4) for t in texts)

        return EmbedResult(
            embeddings=embeddings,
            dimensions=self.dimensions,
            tokens_used=approx_tokens,
            latency_ms=latency_ms,
            cache_hit=False,
            model=self.model_name,
        )

    def embed_query(self, query: str) -> list[float]:
        prefixed = (self.query_prefix or "") + query
        model = self._get_model()
        embs = list(model.embed([prefixed], batch_size=1))
        if not embs:
            raise ValueError(f"Failed to embed query: {query[:50]}")
        return list(embs[0])


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Gemini API embedding provider (delegates to LLMGateway)."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self._gateway = gateway
        cfg = get_embedding_config()
        self._model_name = cfg.get("gemini_model", "gemini-embedding-001")
        self._dimensions = int(cfg.get("dimensions", 768))
        self.doc_task = cfg.get("task_type", "RETRIEVAL_DOCUMENT")
        self.query_task = cfg.get("query_task_type", "RETRIEVAL_QUERY")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def gateway(self) -> LLMGateway:
        if self._gateway is None:
            from src.llm.gateway import LLMGateway

            self._gateway = LLMGateway()
        return self._gateway

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        res = self.gateway.embed(texts, task=self.doc_task)
        res.model = self.model_name
        return res

    def embed_query(self, query: str) -> list[float]:
        res = self.gateway.embed([query], task=self.query_task)
        if not res.embeddings:
            raise ValueError(f"No embedding returned for query: {query[:50]}...")
        return res.embeddings[0]


class EmbeddingsService:
    """High-level service for generating text embeddings for ingestion and retrieval."""

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        gateway: LLMGateway | None = None,
    ) -> None:
        if provider is not None:
            self.provider = provider
        else:
            cfg = get_embedding_config()
            provider_type = cfg.get("provider", "local").lower()
            if provider_type == "local":
                self.provider = FastEmbedProvider()
            elif provider_type == "gemini":
                self.provider = GeminiEmbeddingProvider(gateway=gateway)
            else:
                self.provider = FastEmbedProvider()

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    @property
    def dimensions(self) -> int:
        return self.provider.dimensions

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        """Embed a list of document or chunk texts."""
        return self.provider.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for vector search."""
        return self.provider.embed_query(query)
