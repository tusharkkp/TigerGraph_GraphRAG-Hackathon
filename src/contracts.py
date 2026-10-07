"""
Data contracts for the Agentic GraphRAG Benchmark.

Every pipeline (RAG, GraphRAG, Agentic) must return a PipelineResult.
These models are the single source of truth for all data flowing
through the system. Changes require an ADR.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TokenUsage(BaseModel):
    """Token accounting for a single question across all LLM calls."""

    context_tokens: int = Field(
        ge=0, description="Tokens of retrieved evidence in the final answer prompt"
    )
    llm_input_tokens: int = Field(
        ge=0, description="Sum of prompt tokens over ALL LLM calls for this question"
    )
    llm_output_tokens: int = Field(
        ge=0, description="Sum of output (+thinking) tokens over ALL LLM calls"
    )
    total_tokens: int = Field(
        ge=0, description="Must equal llm_input_tokens + llm_output_tokens"
    )

    @model_validator(mode="after")
    def _check_invariants(self) -> TokenUsage:
        if self.total_tokens != self.llm_input_tokens + self.llm_output_tokens:
            raise ValueError(
                f"total_tokens ({self.total_tokens}) != "
                f"llm_input_tokens ({self.llm_input_tokens}) + "
                f"llm_output_tokens ({self.llm_output_tokens})"
            )
        if self.context_tokens > self.llm_input_tokens:
            raise ValueError(
                f"context_tokens ({self.context_tokens}) > "
                f"llm_input_tokens ({self.llm_input_tokens})"
            )
        return self


class Citation(BaseModel):
    """A citation linking an answer claim to a source chunk."""

    chunk_id: str
    doc_id: str
    quote: str | None = None  # Must be a substring of the chunk text (tested)
    entity_ids: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    """One step in the agentic investigation trace."""

    step: int = Field(ge=0)
    agent: str
    tool: str
    args: dict = Field(default_factory=dict)
    rationale: str = Field(description="Short, user-visible reason (NOT raw chain-of-thought)")
    observation_summary: str
    new_evidence_ids: list[str] = Field(default_factory=list)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    strategy_tag: str = Field(
        description='e.g. "vector_first", "graph_first", "verify", "aggregate"'
    )
    decision: Literal["continue", "change_strategy", "stop"]


class PipelineResult(BaseModel):
    """Output of any pipeline for a single question. The universal result format."""

    question_id: str
    pipeline: Literal["rag", "graphrag", "agentic"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    tokens: TokenUsage
    latency_ms: int = Field(ge=0)
    trace: list[TraceStep] = Field(default_factory=list)
    stop_reason: str | None = None
    strategy_changed: bool = False
    error: str | None = None

    @model_validator(mode="after")
    def _check_pipeline_constraints(self) -> PipelineResult:
        if self.pipeline == "rag" and self.trace:
            raise ValueError("RAG pipeline must have an empty trace")
        if self.pipeline == "agentic" and not self.error:
            if not self.trace:
                raise ValueError("Agentic pipeline must have a non-empty trace")
            if not self.stop_reason:
                raise ValueError("Agentic pipeline must have a stop_reason")
            # Last trace step must be a stop decision
            if self.trace[-1].decision != "stop":
                raise ValueError("Last trace step must have decision='stop'")
        return self


# --- Question & evaluation contracts ---


class Question(BaseModel):
    """A question from the dataset (public or hidden)."""

    qid: str
    question: str
    qtype: str  # aggregation, multi_hop, temporal, lookup, superlative
    # Fields below are only present in public questions
    answer: list[str] | None = None
    gold_doc_ids: list[str] | None = None
    answer_named_in_question: bool | None = None
    guess_baseline: float | None = None
    answer_verified: bool | None = None


class JudgeResult(BaseModel):
    """Output of the LLM judge for one (question, answer) pair."""

    question_id: str
    pipeline: str
    verdict: Literal["PASS", "FAIL"]
    completeness: float = Field(ge=0.0, le=1.0)
    missing_facts: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    reason: str = Field(max_length=200)


# --- LLM gateway contracts ---


class CallTag(BaseModel):
    """Tag for every LLM call, used for logging and accounting."""

    question_id: str | None = None
    pipeline: str | None = None
    step: int | None = None
    agent: str | None = None
    role: str = "answer"


class LLMResult(BaseModel):
    """Result from the LLM gateway."""

    text: str
    parsed: BaseModel | None = None
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cache_hit: bool = False
    model: str = ""


class EmbedResult(BaseModel):
    """Result from the embedding endpoint."""

    embeddings: list[list[float]]
    dimensions: int = Field(ge=1)
    tokens_used: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cache_hit: bool = False
    model: str = ""
