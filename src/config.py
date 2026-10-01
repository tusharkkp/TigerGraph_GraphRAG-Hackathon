"""
Centralised configuration loader.

Reads YAML configs from configs/ and environment variables from .env.
All magic numbers live in config files, not in code.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

# Project root = the directory containing this file's parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "Dataset"
RESULTS_DIR = PROJECT_ROOT / "results"
SUBMISSION_DIR = PROJECT_ROOT / "submission"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = PROJECT_ROOT / ".llm_cache"


class TigerGraphSettings(BaseSettings):
    """TigerGraph connection settings from environment variables."""

    tg_host: str = Field(default="", alias="TG_HOST")
    tg_graphname: str = Field(default="", alias="TG_GRAPHNAME")
    tg_username: str = Field(default="tigergraph", alias="TG_USERNAME")
    tg_password: str = Field(default="", alias="TG_PASSWORD")
    tg_secret: str = Field(default="", alias="TG_SECRET")
    tg_token: str = Field(default="", alias="TG_TOKEN")

    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "extra": "ignore"}


class GeminiSettings(BaseSettings):
    """Gemini API settings from environment variables."""

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "extra": "ignore"}


def _load_yaml(name: str) -> dict[str, Any]:
    """Load a YAML config file from the configs directory."""
    path = CONFIGS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


@cache
def get_models_config() -> dict[str, Any]:
    """Load models.yaml — model names, roles, rate limits."""
    return _load_yaml("models.yaml")


@cache
def get_retrieval_config() -> dict[str, Any]:
    """Load retrieval.yaml — chunking, vector search, graph traversal params."""
    return _load_yaml("retrieval.yaml")


@cache
def get_agent_config() -> dict[str, Any]:
    """Load agent.yaml — budgets, stopping criteria, tool params."""
    return _load_yaml("agent.yaml")


@cache
def get_eval_config() -> dict[str, Any]:
    """Load eval.yaml — splits, judge, benchmark, regression gates."""
    return _load_yaml("eval.yaml")


@cache
def get_tg_settings() -> TigerGraphSettings:
    """Load TigerGraph settings from environment."""
    return TigerGraphSettings()


@cache
def get_gemini_settings() -> GeminiSettings:
    """Load Gemini settings from environment."""
    return GeminiSettings()


def get_model_for_role(role: str) -> dict[str, Any]:
    """Get model config for a specific role (answer, orchestrator, agent, judge, extract)."""
    config = get_models_config()
    roles = config.get("roles", {})
    if role not in roles:
        raise ValueError(f"Unknown role '{role}'. Available: {list(roles.keys())}")
    return roles[role]


def get_embedding_config() -> dict[str, Any]:
    """Get embedding model configuration."""
    config = get_models_config()
    return config.get("embedding", {})
