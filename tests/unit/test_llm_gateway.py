"""Unit tests for LLMGateway and EmbeddingsService — 100% offline with mocks."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field
from src.config import get_model_for_role
from src.contracts import CallTag
from src.llm.cache import DiskCache
from src.llm.embeddings import EmbeddingsService
from src.llm.gateway import LLMGateway, LLMQuotaError, LLMSchemaError


class DummyAnswer(BaseModel):
    summary: str = Field(description="Summary of the answer")
    count: int = Field(ge=0)


def _make_mock_response(
    text: str,
    prompt_tokens: int = 100,
    candidate_tokens: int = 50,
    thinking_tokens: int = 0,
):
    resp = MagicMock()
    resp.text = text
    meta = MagicMock()
    meta.prompt_token_count = prompt_tokens
    meta.candidates_token_count = candidate_tokens
    meta.thoughts_token_count = thinking_tokens
    resp.usage_metadata = meta
    return resp


class TestLLMGateway:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        return client

    @pytest.fixture
    def gateway(self, mock_client, tmp_path: Path):
        cache = DiskCache(cache_dir=tmp_path, enabled=True)
        gw = LLMGateway(
            cache=cache,
            client=mock_client,
            models_config={
                "roles": {
                    "answer": {"model": "gemini-2.0-flash", "temperature": 0.0, "max_output_tokens": 1024},
                    "agent": {"model": "gemini-2.0-flash", "temperature": 0.0, "max_output_tokens": 512},
                },
                "embedding": {"model": "text-embedding-004", "dimensions": 768},
                "rate_limits": {
                    "max_concurrent": 2,
                    "retry_max_attempts": 3,
                    "retry_base_delay": 0.01,
                    "retry_max_delay": 0.05,
                },
            },
        )
        return gw

    def test_generate_text_success_and_token_accounting(self, gateway, mock_client):
        mock_client.models.generate_content.return_value = _make_mock_response(
            text="The 2012 Olympics had 302 events.",
            prompt_tokens=150,
            candidate_tokens=30,
            thinking_tokens=15,
        )

        res = gateway.generate(
            role="answer",
            prompt="How many events were in 2012?",
            tag=CallTag(question_id="q1", pipeline="rag"),
        )

        assert res.text == "The 2012 Olympics had 302 events."
        assert res.tokens_in == 150
        assert res.tokens_out == 45  # 30 + 15 thinking
        assert not res.cache_hit
        assert res.model == get_model_for_role("answer")["model"]
        mock_client.models.generate_content.assert_called_once()

    def test_cache_hit_bypasses_second_api_call(self, gateway, mock_client):
        mock_client.models.generate_content.return_value = _make_mock_response(
            text="First call response",
            prompt_tokens=100,
            candidate_tokens=20,
        )

        # Call 1: cache miss
        r1 = gateway.generate(role="answer", prompt="Cached prompt")
        assert not r1.cache_hit
        assert mock_client.models.generate_content.call_count == 1

        # Call 2: cache hit
        r2 = gateway.generate(role="answer", prompt="Cached prompt")
        assert r2.cache_hit
        assert r2.text == "First call response"
        assert r2.tokens_in == 100
        assert r2.tokens_out == 20
        # Call count remains 1
        assert mock_client.models.generate_content.call_count == 1

    def test_retry_on_429_success(self, gateway, mock_client):
        mock_client.models.generate_content.side_effect = [
            Exception("429 ResourceExhausted: rate limit exceeded"),
            _make_mock_response("Recovered after retry", prompt_tokens=80, candidate_tokens=20),
        ]

        res = gateway.generate(role="answer", prompt="Retry test prompt")
        assert res.text == "Recovered after retry"
        assert mock_client.models.generate_content.call_count == 2

    def test_retry_exhausted_raises_quota_error(self, gateway, mock_client):
        mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted")

        with pytest.raises(LLMQuotaError, match="Exhausted 3 retries"):
            gateway.generate(role="answer", prompt="Doomed prompt")

    def test_structured_output_parsing_success(self, gateway, mock_client):
        valid_json = '{"summary": "Total gold medals", "count": 25}'
        mock_client.models.generate_content.return_value = _make_mock_response(valid_json)

        res = gateway.generate(
            role="agent",
            prompt="Return count as JSON",
            schema=DummyAnswer,
        )

        assert isinstance(res.parsed, DummyAnswer)
        assert res.parsed.summary == "Total gold medals"
        assert res.parsed.count == 25

    def test_structured_output_repair_flow(self, gateway, mock_client):
        malformed_json = '{"summary": "broken JSON", count: NOPE}'
        fixed_json = '{"summary": "repaired", "count": 10}'

        mock_client.models.generate_content.side_effect = [
            _make_mock_response(malformed_json, prompt_tokens=50, candidate_tokens=20),
            _make_mock_response(fixed_json, prompt_tokens=100, candidate_tokens=25),
        ]

        res = gateway.generate(
            role="agent",
            prompt="Return count as JSON",
            schema=DummyAnswer,
        )

        assert isinstance(res.parsed, DummyAnswer)
        assert res.parsed.summary == "repaired"
        assert res.parsed.count == 10
        # Tokens from both calls must be summed
        assert res.tokens_in == 150
        assert res.tokens_out == 45
        assert mock_client.models.generate_content.call_count == 2

    def test_structured_output_double_failure_raises_schema_error(self, gateway, mock_client):
        mock_client.models.generate_content.side_effect = [
            _make_mock_response("not json 1"),
            _make_mock_response("not json 2"),
        ]

        with pytest.raises(LLMSchemaError, match="Failed to produce valid DummyAnswer after repair"):
            gateway.generate(
                role="agent",
                prompt="Broken schema prompt",
                schema=DummyAnswer,
            )

    def test_embed_documents_and_query(self, gateway, mock_client):
        emb_resp = MagicMock()
        item1 = MagicMock()
        item1.values = [0.1] * 768
        item2 = MagicMock()
        item2.values = [0.2] * 768
        emb_resp.embeddings = [item1, item2]
        emb_resp.usage_metadata.prompt_token_count = 35
        mock_client.models.embed_content.return_value = emb_resp

        res = gateway.embed(["doc 1", "doc 2"])
        assert len(res.embeddings) == 2
        assert res.dimensions == 768
        assert res.tokens_used == 35

        # Test EmbeddingsService helper
        service = EmbeddingsService(gateway=gateway)
        query_vec = service.embed_query("Olympic rowing")
        assert len(query_vec) == 768
