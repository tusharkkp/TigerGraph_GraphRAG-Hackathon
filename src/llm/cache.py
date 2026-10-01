"""
On-disk cache for LLM and embedding requests.

Keyed by SHA-256 hash of (model, params, prompt, schema).
Persists responses and token usage metadata to avoid redundant API calls
and enable reproducible benchmarks without spending quota.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.config import CACHE_DIR

logger = logging.getLogger(__name__)


class DiskCache:
    """Thread-safe disk cache for LLM and embedding results."""

    def __init__(self, cache_dir: Path | str | None = None, enabled: bool = True) -> None:
        self.cache_dir = Path(cache_dir or CACHE_DIR)
        self.enabled = enabled
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_key(
        model: str,
        prompt: str | list[Any],
        schema_name: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Compute a deterministic SHA-256 key from request parameters."""
        normalized: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "schema_name": schema_name,
            "kwargs": {k: v for k, v in sorted(kwargs.items()) if v is not None},
        }
        serialized = json.dumps(normalized, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a cached response by key. Returns None on cache miss or error."""
        if not self.enabled:
            return None

        file_path = self.cache_dir / f"{key}.json"
        if not file_path.exists():
            with self._lock:
                self._misses += 1
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._hits += 1
            return data
        except Exception as e:
            logger.warning("Failed to read cache file %s: %s", file_path, e)
            with self._lock:
                self._misses += 1
            return None

    def set(self, key: str, data: dict[str, Any]) -> None:
        """Store a response in cache."""
        if not self.enabled:
            return

        file_path = self.cache_dir / f"{key}.json"
        temp_path = self.cache_dir / f"{key}.tmp"
        try:
            with self._lock:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                temp_path.replace(file_path)
        except Exception as e:
            logger.warning("Failed to write cache file %s: %s", file_path, e)
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()

    def clear(self) -> int:
        """Clear all entries in the cache directory. Returns count of deleted files."""
        if not self.cache_dir.exists():
            return 0

        count = 0
        with self._lock:
            for child in self.cache_dir.glob("*.json"):
                try:
                    child.unlink()
                    count += 1
                except OSError as e:
                    logger.warning("Failed to remove cache entry %s: %s", child, e)
            self._hits = 0
            self._misses = 0
        return count

    @property
    def stats(self) -> dict[str, int]:
        """Return cache hit and miss statistics."""
        with self._lock:
            return {"hits": self._hits, "misses": self._misses}
