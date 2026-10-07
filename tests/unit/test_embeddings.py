"""
Unit tests for EmbeddingProvider and EmbeddingsService (ADR-007).
"""

from unittest.mock import MagicMock, patch
import pytest

from src.contracts import EmbedResult
from src.llm.embeddings import (
    EmbeddingProvider,
    FastEmbedProvider,
    GeminiEmbeddingProvider,
    EmbeddingsService,
)


def test_fastembed_provider_properties():
    provider = FastEmbedProvider(
        model_name="BAAI/bge-base-en-v1.5",
        dimensions=768,
        query_prefix="query: ",
        doc_prefix="doc: ",
    )
    assert provider.model_name == "BAAI/bge-base-en-v1.5"
    assert provider.dimensions == 768


def test_fastembed_provider_empty():
    provider = FastEmbedProvider()
    res = provider.embed_documents([])
    assert res.embeddings == []
    assert res.dimensions == 768
    assert res.tokens_used == 0


def test_embeddings_service_defaults():
    service = EmbeddingsService()
    assert service.dimensions == 768
    assert "bge" in service.model_name.lower() or "nomic" in service.model_name.lower()


def test_gemini_provider_delegation():
    mock_gateway = MagicMock()
    mock_gateway.embed.return_value = EmbedResult(
        embeddings=[[0.1] * 768],
        dimensions=768,
        tokens_used=10,
        latency_ms=50,
        model="gemini-embedding-001",
    )
    provider = GeminiEmbeddingProvider(gateway=mock_gateway)
    res = provider.embed_documents(["test text"])
    assert len(res.embeddings) == 1
    assert len(res.embeddings[0]) == 768
    assert res.model == "gemini-embedding-001"

    q_emb = provider.embed_query("test query")
    assert len(q_emb) == 768
