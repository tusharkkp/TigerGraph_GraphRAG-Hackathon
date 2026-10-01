"""Integration smoke tests for Gemini LLM Gateway — runs only when GEMINI_API_KEY is set."""

import os

import pytest
from src.contracts import CallTag
from src.llm.gateway import LLMGateway

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not configured in environment or .env",
)
class TestGeminiLiveSmoke:
    def test_live_generate_and_token_accounting(self):
        gw = LLMGateway(cache_enabled=False)
        tag = CallTag(role="answer", question_id="smoke-test", pipeline="rag")
        res = gw.generate(
            role="answer",
            prompt="Reply with exactly 'OK' and nothing else.",
            tag=tag,
        )

        assert res.text.strip()
        assert res.tokens_in > 0
        assert res.tokens_out > 0
        assert res.latency_ms > 0
        assert not res.cache_hit

    def test_live_embed_documents(self):
        gw = LLMGateway(cache_enabled=False)
        res = gw.embed(["Olympic tennis tournament 2012", "Archery men's individual"])

        assert len(res.embeddings) == 2
        assert res.dimensions == 768
        assert res.tokens_used >= 0
