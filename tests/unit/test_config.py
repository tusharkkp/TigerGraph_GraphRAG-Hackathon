"""Unit tests for the config loader."""

import pytest
from src.config import (
    get_agent_config,
    get_embedding_config,
    get_eval_config,
    get_model_for_role,
    get_models_config,
    get_retrieval_config,
)


class TestConfigLoader:
    def test_models_config_loads(self):
        config = get_models_config()
        assert "roles" in config
        assert "embedding" in config

    def test_retrieval_config_loads(self):
        config = get_retrieval_config()
        assert "chunking" in config
        assert "vector_search" in config

    def test_agent_config_loads(self):
        config = get_agent_config()
        assert "budgets" in config
        assert "stopping" in config

    def test_eval_config_loads(self):
        config = get_eval_config()
        assert "splits" in config
        assert config["splits"]["seed"] == 42

    def test_model_for_role(self):
        for role in ["answer", "orchestrator", "agent", "judge", "extract"]:
            model_config = get_model_for_role(role)
            assert "model" in model_config
            assert "temperature" in model_config

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError, match="Unknown role"):
            get_model_for_role("nonexistent_role")

    def test_embedding_config(self):
        config = get_embedding_config()
        assert "model" in config
        assert "dimensions" in config
        assert config["dimensions"] > 0
