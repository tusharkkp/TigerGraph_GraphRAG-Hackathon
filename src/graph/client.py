"""
TigerGraph Savanna client wrapper.

Encapsulates pyTigerGraph connection management, token authentication,
vertex/edge batch upserts, parametrised query execution, and schema inspection.
"""

from __future__ import annotations

import logging
from typing import Any

import pyTigerGraph

from src.config import TigerGraphSettings, get_tg_settings

logger = logging.getLogger(__name__)


class TigerGraphClient:
    """Production client for TigerGraph Savanna."""

    def __init__(
        self,
        settings: TigerGraphSettings | None = None,
        conn: pyTigerGraph.TigerGraphConnection | None = None,
    ) -> None:
        self.settings = settings or get_tg_settings()
        self._conn = conn
        self._token_refreshed = False

    @property
    def conn(self) -> pyTigerGraph.TigerGraphConnection:
        """Lazily initialize and return the authenticated TigerGraphConnection."""
        if self._conn is None:
            self._connect()
        return self._conn

    def _connect(self) -> None:
        """Create and authenticate a pyTigerGraph connection to Savanna."""
        host = self.settings.tg_host
        if not host:
            raise ValueError("TG_HOST is not configured in environment or .env")

        graphname = self.settings.tg_graphname or "GraphRAG"
        is_cloud = "tgcloud.io" in host

        self._conn = pyTigerGraph.TigerGraphConnection(
            host=host,
            graphname=graphname,
            username=self.settings.tg_username or "tigergraph",
            password=self.settings.tg_password,
            tgCloud=is_cloud,
            restppPort=443 if is_cloud else 9000,
            gsPort=443 if is_cloud else 14240,
        )

        # Apply token / secret authentication
        if self.settings.tg_token:
            self._conn.apiToken = self.settings.tg_token
        elif self.settings.tg_secret:
            try:
                token, _ = self._conn.getToken(self.settings.tg_secret)
                self._conn.apiToken = token
            except Exception as e:
                logger.warning("Failed to get token with TG_SECRET: %s", e)
        elif self.settings.tg_password:
            try:
                secret = self._conn.createSecret()
                token, _ = self._conn.getToken(secret)
                self._conn.apiToken = token
            except Exception as e:
                logger.debug("Failed auto createSecret/getToken with password: %s", e)

    def _with_reauth(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a function with automatic token refresh on 401 / expired token."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            if ("401" in err_msg or "token" in err_msg or "unauthorized" in err_msg) and not self._token_refreshed:
                logger.info("TigerGraph token may have expired. Attempting refresh...")
                self._token_refreshed = True
                try:
                    secret = self.conn.createSecret()
                    token, _ = self.conn.getToken(secret)
                    self.conn.apiToken = token
                    return fn(*args, **kwargs)
                except Exception as refresh_err:
                    logger.error("Token refresh failed: %s", refresh_err)
                    raise e from refresh_err
            raise

    def schema_summary(self) -> dict[str, Any]:
        """Return a dictionary summarizing vertex and edge types in the schema."""
        raw_schema = self._with_reauth(self.conn.getSchema)
        vertices = []
        edges = []

        if isinstance(raw_schema, dict):
            for v in raw_schema.get("VertexTypes", []):
                vertices.append({
                    "name": v.get("Name"),
                    "primary_id": v.get("PrimaryId", {}).get("AttributeName"),
                    "attributes": [a.get("AttributeName") for a in v.get("Attributes", [])],
                })
            for e in raw_schema.get("EdgeTypes", []):
                edges.append({
                    "name": e.get("Name"),
                    "from_vertex": e.get("FromVertexTypeName"),
                    "to_vertex": e.get("ToVertexTypeName"),
                    "is_directed": e.get("IsDirectedEdge", False),
                })

        return {"vertices": vertices, "edges": edges}

    def run_query(self, query_name: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run an installed GSQL query with parameters."""
        p = params or {}
        return self._with_reauth(self.conn.runInstalledQuery, query_name, params=p)

    def upsert_vertex(self, vertex_type: str, vertex_id: str, attributes: dict[str, Any]) -> int:
        """Upsert a single vertex."""
        return self.upsert_vertices(vertex_type, [(vertex_id, attributes)])

    def upsert_vertices(self, vertex_type: str, vertices: list[tuple[str, dict[str, Any]]]) -> int:
        """
        Batch upsert vertices of a specific type.
        Args:
            vertex_type: Vertex type name (e.g. 'DocumentChunk').
            vertices: List of (primary_id, attributes_dict) tuples.
        """
        if not vertices:
            return 0

        formatted = [
            (vid, {k: v for k, v in attrs.items() if v is not None})
            for vid, attrs in vertices
        ]
        res = self._with_reauth(self.conn.upsertVertices, vertex_type, formatted)
        return int(res) if isinstance(res, (int, float)) else len(vertices)

    def upsert_edge(
        self,
        source_type: str,
        source_id: str,
        edge_type: str,
        target_type: str,
        target_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Upsert a single edge."""
        return self.upsert_edges([(source_type, source_id, edge_type, target_type, target_id, attributes or {})])

    def upsert_edges(
        self,
        edges: list[tuple[str, str, str, str, str, dict[str, Any]]],
    ) -> int:
        """
        Batch upsert edges.
        Args:
            edges: List of (source_type, source_id, edge_type, target_type, target_id, attributes) tuples.
        """
        if not edges:
            return 0

        # pyTigerGraph upsertEdges takes (source_type, edge_type, target_type, data)
        # We group by (source_type, edge_type, target_type)
        grouped: dict[tuple[str, str, str], list[tuple[str, str, dict[str, Any]]]] = {}
        for st, sid, et, tt, tid, attrs in edges:
            key = (st, et, tt)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append((sid, tid, attrs))

        total_upserted = 0
        for (st, et, tt), edge_list in grouped.items():
            res = self._with_reauth(self.conn.upsertEdges, st, et, tt, edge_list)
            total_upserted += int(res) if isinstance(res, (int, float)) else len(edge_list)

        return total_upserted

    def get_vertex_count(self, vertex_type: str) -> int:
        """Get total vertex count for a vertex type."""
        try:
            return int(self._with_reauth(self.conn.getVertexCount, vertex_type))
        except Exception:
            return 0

    def get_edge_count(self, edge_type: str) -> int:
        """Get total edge count for an edge type."""
        try:
            return int(self._with_reauth(self.conn.getEdgeCount, edge_type))
        except Exception:
            return 0
