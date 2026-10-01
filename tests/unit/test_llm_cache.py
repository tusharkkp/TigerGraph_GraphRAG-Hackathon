"""Unit tests for DiskCache — completely offline."""

from pathlib import Path

from src.llm.cache import DiskCache


class TestDiskCache:
    def test_key_computation_deterministic(self):
        k1 = DiskCache.compute_key(
            model="gemini-2.0-flash",
            prompt="Hello world",
            schema_name="TestSchema",
            temperature=0.0,
            max_tokens=100,
        )
        # Same values, different kwarg order
        k2 = DiskCache.compute_key(
            model="gemini-2.0-flash",
            prompt="Hello world",
            schema_name="TestSchema",
            max_tokens=100,
            temperature=0.0,
        )
        assert k1 == k2

    def test_key_computation_changes_with_prompt_or_model(self):
        k1 = DiskCache.compute_key(model="gemini-2.0-flash", prompt="Prompt A")
        k2 = DiskCache.compute_key(model="gemini-2.0-flash", prompt="Prompt B")
        k3 = DiskCache.compute_key(model="gemini-2.5-flash", prompt="Prompt A")
        assert k1 != k2
        assert k1 != k3

    def test_set_and_get(self, tmp_path: Path):
        cache = DiskCache(cache_dir=tmp_path, enabled=True)
        key = "test_key_123"
        data = {
            "text": "Answer text",
            "tokens_in": 50,
            "tokens_out": 25,
            "latency_ms": 120,
            "model": "gemini-2.0-flash",
        }

        # Initially miss
        assert cache.get(key) is None
        assert cache.stats["misses"] == 1
        assert cache.stats["hits"] == 0

        # Store and hit
        cache.set(key, data)
        retrieved = cache.get(key)
        assert retrieved is not None
        assert retrieved["text"] == "Answer text"
        assert retrieved["tokens_in"] == 50
        assert cache.stats["hits"] == 1

    def test_disabled_cache(self, tmp_path: Path):
        cache = DiskCache(cache_dir=tmp_path, enabled=False)
        key = "test_key_disabled"
        data = {"text": "hello"}

        cache.set(key, data)
        assert cache.get(key) is None
        assert not (tmp_path / f"{key}.json").exists()

    def test_clear_cache(self, tmp_path: Path):
        cache = DiskCache(cache_dir=tmp_path, enabled=True)
        cache.set("k1", {"val": 1})
        cache.set("k2", {"val": 2})

        assert len(list(tmp_path.glob("*.json"))) == 2
        deleted = cache.clear()
        assert deleted == 2
        assert len(list(tmp_path.glob("*.json"))) == 0
