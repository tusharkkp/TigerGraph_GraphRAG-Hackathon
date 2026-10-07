"""
Pipeline 3: Quota-Aware Agentic GraphRAG.

Combines:
1. Deterministic Entity Linking (0 LLM calls)
2. Master Orchestrator Planning (LLM Call 1)
3. Composable Parameterized GSQL Queries in TigerGraph Savanna
4. Deterministic Evidence Evaluation & Dynamic Vector Fallback
5. Evidence-Grounded Answer Synthesis with Citations (LLM Call 2)
6. Strict Quota Guarantee: <= 3 LLM calls per question.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agentic.orchestrator import AgenticOrchestrator
from src.agentic.tools import TigerGraphToolSuite
from src.contracts import PipelineResult, Question
from src.graph.client import TigerGraphClient
from src.llm.embeddings import EmbeddingsService
from src.llm.gateway import LLMGateway
from src.pipelines.answer_generator import AnswerGenerator

logger = logging.getLogger(__name__)


class AgenticGraphRAGPipeline:
    """Production Agentic GraphRAG Pipeline implementing the universal Pipeline contract."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        tg_client: TigerGraphClient | None = None,
        embeddings_service: EmbeddingsService | None = None,
        answer_generator: AnswerGenerator | None = None,
        max_steps: int = 3,
        token_cap: int = 5000,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.tg_client = tg_client or TigerGraphClient()
        self.embeddings = embeddings_service or EmbeddingsService(gateway=self.gateway)
        self.tools = TigerGraphToolSuite(client=self.tg_client, embeddings=self.embeddings)
        self.answer_generator = answer_generator or AnswerGenerator(gateway=self.gateway)
        self.orchestrator = AgenticOrchestrator(
            gateway=self.gateway,
            tool_suite=self.tools,
            answer_generator=self.answer_generator,
            max_steps=max_steps,
            token_cap=token_cap,
        )

    def run(self, question: Question | dict[str, Any], top_k: int = 5) -> PipelineResult:
        """
        Execute Agentic GraphRAG pipeline for a question.
        """
        if isinstance(question, Question):
            qid = question.qid
            qtext = question.question
        else:
            qid = question["qid"]
            qtext = question["question"]

        logger.info("[P3 Agentic GraphRAG] Running for %s: %s", qid, qtext)
        return self.orchestrator.run(question=qtext, question_id=qid)


if __name__ == "__main__":
    pipeline = AgenticGraphRAGPipeline()
    sample_q = {
        "qid": "pub-065",
        "question": "According to the provided corpus, how many biathlon events at the 2014 Winter Olympics had more than 68 competitors?",
    }
    result = pipeline.run(sample_q)
    print("\nAgentic GraphRAG Result:")
    print(result.model_dump_json(indent=2))
