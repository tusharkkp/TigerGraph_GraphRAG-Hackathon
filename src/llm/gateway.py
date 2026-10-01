"""
Single LLM gateway for all Gemini model interactions.

Strict adherence to AGENT.md:
- Only this module may import the Google GenAI SDK.
- Model names are config-driven from configs/models.yaml, never hardcoded.
- Exact token accounting from usage_metadata (prompt + candidates + thinking).
- Invariant: total_tokens == llm_input_tokens + llm_output_tokens.
- Retry with exponential backoff + jitter on 429/5xx.
- Concurrency limiting via threading.Semaphore.
- On-disk response cache keyed by SHA-256(model, params, prompt, schema).
- Structured JSON output validation with Pydantic + single repair attempt.
- Structured JSON line logging to logs/llm_calls.jsonl.
"""

from __future__ import annotations

import datetime
import json
import logging
import random
import re
import threading
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.config import (
    LOGS_DIR,
    GeminiSettings,
    get_embedding_config,
    get_gemini_settings,
    get_model_for_role,
    get_models_config,
)
from src.contracts import CallTag, EmbedResult, LLMResult
from src.llm.cache import DiskCache

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMSchemaError(Exception):
    """Raised when an LLM output cannot be parsed/repaired into the expected Pydantic schema."""


class LLMQuotaError(Exception):
    """Raised when retries on 429 / resource exhausted are exhausted."""


class LLMGateway:
    """The central gateway for all LLM and embedding operations."""

    def __init__(
        self,
        settings: GeminiSettings | None = None,
        models_config: dict[str, Any] | None = None,
        cache: DiskCache | None = None,
        client: genai.Client | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.settings = settings or get_gemini_settings()
        self.models_config = models_config or get_models_config()
        self.cache = cache or DiskCache(enabled=cache_enabled)

        # Rate limits & retries
        rate_limits = self.models_config.get("rate_limits", {})
        max_concurrent = int(rate_limits.get("max_concurrent", 5))
        self._semaphore = threading.Semaphore(max_concurrent)
        self.retry_max_attempts = int(rate_limits.get("retry_max_attempts", 5))
        self.retry_base_delay = float(rate_limits.get("retry_base_delay", 1.0))
        self.retry_max_delay = float(rate_limits.get("retry_max_delay", 60.0))

        # Client: injected (for tests) or initialized with API key
        if client is not None:
            self._client = client
        elif self.settings.gemini_api_key:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        else:
            self._client = None

        # Logging setup
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.log_file = LOGS_DIR / "llm_calls.jsonl"
        self._log_lock = threading.Lock()

    @property
    def client(self) -> genai.Client:
        """Return the active genai.Client or raise ValueError if credentials are missing."""
        if self._client is None:
            raise ValueError(
                "Gemini API client not initialized. GEMINI_API_KEY is missing or empty."
            )
        return self._client

    def _extract_tokens(self, response: Any) -> tuple[int, int]:
        """Extract input and output tokens (including thinking) from usage_metadata."""
        metadata = getattr(response, "usage_metadata", None)
        if not metadata:
            return 0, 0

        raw_in = getattr(metadata, "prompt_token_count", 0)
        tokens_in = 0 if hasattr(raw_in, "_mock_return_value") else int(raw_in or 0)

        raw_cand = getattr(metadata, "candidates_token_count", 0)
        candidates = 0 if hasattr(raw_cand, "_mock_return_value") else int(raw_cand or 0)

        raw_thinking = getattr(metadata, "thoughts_token_count", 0)
        thinking = 0 if hasattr(raw_thinking, "_mock_return_value") else int(raw_thinking or 0)

        tokens_out = candidates + thinking
        return tokens_in, tokens_out

    def _log_call(
        self,
        *,
        tag: CallTag | None,
        model: str,
        role: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        cache_hit: bool,
    ) -> None:
        """Write structured JSON log entry for this LLM call."""
        entry = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "role": role,
            "model": model,
            "question_id": tag.question_id if tag else None,
            "pipeline": tag.pipeline if tag else None,
            "step": tag.step if tag else None,
            "agent": tag.agent if tag else None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "latency_ms": latency_ms,
            "cache_hit": cache_hit,
        }
        with self._log_lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.warning("Failed to write to %s: %s", self.log_file, e)

    def _call_with_retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a function with exponential backoff and jitter on 429/5xx errors."""
        last_error = None
        for attempt in range(self.retry_max_attempts):
            try:
                with self._semaphore:
                    return fn(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                is_retryable = any(
                    code in err_str
                    for code in ["429", "resource_exhausted", "quota", "500", "503", "unavailable", "timeout"]
                )
                if not is_retryable:
                    raise

                last_error = e
                if attempt == self.retry_max_attempts - 1:
                    raise LLMQuotaError(
                        f"Exhausted {self.retry_max_attempts} retries: {last_error}"
                    ) from last_error

                # Exponential backoff + jitter
                delay = min(
                    self.retry_max_delay,
                    self.retry_base_delay * (2 ** attempt) + random.uniform(0.0, 0.05),
                )
                match = re.search(r"retry in ([\d\.]+)s", str(e), re.IGNORECASE) or re.search(r"['\"]retryDelay['\"]:\s*['\"](\d+)s", str(e))
                if match:
                    delay = min(self.retry_max_delay + 30.0, float(match.group(1)) + 1.0)

                logger.warning(
                    "LLM call failed (attempt %d/%d): %s. Retrying in %.2fs...",
                    attempt + 1,
                    self.retry_max_attempts,
                    e,
                    delay,
                )
                time.sleep(delay)

        raise LLMQuotaError(f"Exhausted {self.retry_max_attempts} retries: {last_error}")


    def generate(
        self,
        *,
        role: str,
        prompt: str | list[Any],
        system_instruction: str | None = None,
        schema: type[T] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tag: CallTag | None = None,
    ) -> LLMResult:
        """
        Generate text or structured output from a Gemini model.

        Args:
            role: Configured role ('answer', 'orchestrator', 'agent', 'judge', 'extract').
            prompt: User prompt text or contents.
            system_instruction: Optional system instruction.
            schema: Optional Pydantic model subclass for structured output.
            temperature: Override temperature (defaults to role config).
            max_output_tokens: Override max output tokens.
            tag: Metadata tag for token accounting and logging.
        """
        role_cfg = get_model_for_role(role)
        model_name = role_cfg["model"]
        eff_temp = float(temperature if temperature is not None else role_cfg.get("temperature", 0.0))
        eff_max_tokens = int(
            max_output_tokens if max_output_tokens is not None else role_cfg.get("max_output_tokens", 2048)
        )

        schema_name = schema.__name__ if schema is not None else None
        cache_key = self.cache.compute_key(
            model=model_name,
            prompt=prompt,
            system_instruction=system_instruction,
            schema_name=schema_name,
            temperature=eff_temp,
            max_output_tokens=eff_max_tokens,
        )

        # 1. Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            parsed_obj = None
            if schema is not None and cached.get("parsed") is not None:
                parsed_obj = schema.model_validate(cached["parsed"])

            self._log_call(
                tag=tag,
                model=model_name,
                role=role,
                tokens_in=cached["tokens_in"],
                tokens_out=cached["tokens_out"],
                latency_ms=0,
                cache_hit=True,
            )
            return LLMResult(
                text=cached["text"],
                parsed=parsed_obj,
                tokens_in=cached["tokens_in"],
                tokens_out=cached["tokens_out"],
                latency_ms=0,
                cache_hit=True,
                model=model_name,
            )

        # 2. Build GenerateContentConfig
        config_kwargs: dict[str, Any] = {
            "temperature": eff_temp,
            "max_output_tokens": eff_max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = schema

        config = types.GenerateContentConfig(**config_kwargs)

        # 3. Call with retry
        start_time = time.perf_counter()
        response = self._call_with_retry(
            self.client.models.generate_content,
            model=model_name,
            contents=prompt,
            config=config,
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        raw_text = response.text or ""
        tokens_in, tokens_out = self._extract_tokens(response)

        # 4. Structured output validation + single repair attempt
        parsed_obj = None
        if schema is not None:
            try:
                parsed_obj = schema.model_validate_json(raw_text)
            except (ValidationError, json.JSONDecodeError) as first_err:
                logger.warning(
                    "Initial structured output parsing failed for %s: %s. Attempting repair...",
                    schema_name,
                    first_err,
                )
                repair_prompt = [
                    f"Your previous output failed schema validation for {schema_name}.",
                    f"Validation error:\n{first_err}",
                    f"Previous malformed output:\n{raw_text}",
                    f"Please return ONLY the corrected, valid JSON object matching the {schema_name} schema.",
                ]
                repair_resp = self._call_with_retry(
                    self.client.models.generate_content,
                    model=model_name,
                    contents=repair_prompt,
                    config=config,
                )
                r_in, r_out = self._extract_tokens(repair_resp)
                tokens_in += r_in
                tokens_out += r_out
                raw_text = repair_resp.text or ""

                try:
                    parsed_obj = schema.model_validate_json(raw_text)
                except (ValidationError, json.JSONDecodeError) as second_err:
                    raise LLMSchemaError(
                        f"Failed to produce valid {schema_name} after repair attempt: {second_err}"
                    ) from second_err

        # 5. Save to cache
        cache_data = {
            "text": raw_text,
            "parsed": parsed_obj.model_dump() if parsed_obj is not None else None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "model": model_name,
        }
        self.cache.set(cache_key, cache_data)

        # 6. Log call
        self._log_call(
            tag=tag,
            model=model_name,
            role=role,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cache_hit=False,
        )

        return LLMResult(
            text=raw_text,
            parsed=parsed_obj,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cache_hit=False,
            model=model_name,
        )

    def embed(
        self,
        texts: list[str],
        *,
        task: str = "RETRIEVAL_DOCUMENT",
    ) -> EmbedResult:
        """
        Embed a list of text strings using the configured embedding model.

        Args:
            texts: List of strings to embed.
            task: Task type (e.g. 'RETRIEVAL_DOCUMENT' or 'RETRIEVAL_QUERY').
        """
        if not texts:
            return EmbedResult(
                embeddings=[],
                dimensions=768,
                tokens_used=0,
                latency_ms=0,
                cache_hit=False,
            )

        embed_cfg = get_embedding_config()
        model_name = embed_cfg["model"]
        expected_dim = int(embed_cfg.get("dimensions", 768))

        cache_key = self.cache.compute_key(
            model=model_name,
            prompt=texts,
            task=task,
        )

        cached = self.cache.get(cache_key)
        if cached is not None:
            return EmbedResult(
                embeddings=cached["embeddings"],
                dimensions=cached["dimensions"],
                tokens_used=cached["tokens_used"],
                latency_ms=0,
                cache_hit=True,
            )

        config = types.EmbedContentConfig(
            task_type=task,
            output_dimensionality=expected_dim,
        )

        start_time = time.perf_counter()
        response = self._call_with_retry(
            self.client.models.embed_content,
            model=model_name,
            contents=texts,
            config=config,
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Parse embeddings from response
        embeddings: list[list[float]] = []
        if hasattr(response, "embeddings") and response.embeddings:
            for item in response.embeddings:
                values = getattr(item, "values", None) or []
                embeddings.append(list(values))
        elif hasattr(response, "embedding") and response.embedding:
            embeddings.append(list(response.embedding.values or []))

        dimensions = len(embeddings[0]) if embeddings else expected_dim

        # Token accounting for embeddings if reported
        metadata = getattr(response, "usage_metadata", None)
        tokens_used = getattr(metadata, "prompt_token_count", 0) or 0

        cache_data = {
            "embeddings": embeddings,
            "dimensions": dimensions,
            "tokens_used": int(tokens_used),
            "latency_ms": latency_ms,
        }
        self.cache.set(cache_key, cache_data)

        return EmbedResult(
            embeddings=embeddings,
            dimensions=dimensions,
            tokens_used=int(tokens_used),
            latency_ms=latency_ms,
            cache_hit=False,
        )
