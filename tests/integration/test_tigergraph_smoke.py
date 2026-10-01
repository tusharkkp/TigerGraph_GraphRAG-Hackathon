"""Integration smoke test for TigerGraph Savanna — runs only when a valid TG_HOST is set."""

import os

import pytest
import pyTigerGraph
from src.config import get_tg_settings

pytestmark = pytest.mark.integration


def _is_valid_tg_host(host: str) -> bool:
    return bool(host and "tgcloud.io/groups" not in host)


@pytest.mark.skipif(
    not _is_valid_tg_host(os.getenv("TG_HOST", "")),
    reason="TG_HOST is not set or is set to console URL instead of REST endpoint",
)
class TestTigerGraphLiveSmoke:
    def test_connection_and_version(self):
        settings = get_tg_settings()
        is_cloud = "tgcloud.io" in settings.tg_host
        conn = pyTigerGraph.TigerGraphConnection(
            host=settings.tg_host,
            graphname=settings.tg_graphname or "GraphRAG",
            username=settings.tg_username or "tigergraph",
            password=settings.tg_password,
            tgCloud=is_cloud,
            restppPort=443 if is_cloud else 9000,
            gsPort=443 if is_cloud else 14240,
            apiToken=settings.tg_token,
        )

        ver = conn.getVer()
        assert ver, "Failed to retrieve TigerGraph version from instance"
