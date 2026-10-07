"""
Schema and query deployment script for TigerGraph Savanna.

Idempotently installs or updates the GraphRAG schema and GSQL queries.
"""

from __future__ import annotations

import argparse
import logging
import re

from src.config import PROJECT_ROOT, get_tg_settings
from src.graph.client import TigerGraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GRAPH_DIR = PROJECT_ROOT / "graph"
SCHEMA_FILE = GRAPH_DIR / "schema.gsql"
QUERIES_DIR = GRAPH_DIR / "queries"


def install_schema(client: TigerGraphClient, dry_run: bool = False) -> None:
    """Read and apply graph/schema.gsql."""
    if not SCHEMA_FILE.exists():
        logger.error("Schema file not found at %s", SCHEMA_FILE)
        return

    with open(SCHEMA_FILE, encoding="utf-8") as f:
        gsql = f.read()

    logger.info("Deploying schema from %s (%d bytes)...", SCHEMA_FILE.name, len(gsql))
    if dry_run:
        logger.info("[Dry Run] Would execute schema DDL:\n%s", gsql[:300])
        return

    graphname = client.settings.tg_graphname or "GraphRAG"
    existing_vertices = client.conn.getVertexTypes(force=True)
    if "Document" in existing_vertices and "DocumentChunk" in existing_vertices and "Entity" in existing_vertices:
        logger.info("Core vertex types already exist in %s: %s. Schema is up to date.", graphname, existing_vertices)
        return

    wrapped_ddl = f"USE GRAPH {graphname}\n{gsql}"
    try:
        res = client.conn.gsql(wrapped_ddl)
        logger.info("Schema deployment result:\n%s", res)
        # Verify deployed types
        updated_vertices = client.conn.getVertexTypes(force=True)
        updated_edges = client.conn.getEdgeTypes(force=True)
        logger.info("Verified deployed vertices: %s", updated_vertices)
        logger.info("Verified deployed edges: %s", updated_edges)
    except Exception as e:
        logger.error("Schema deployment failed: %s", e)
        raise


def _query_name(q_code: str, fallback: str) -> str:
    m = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:DISTRIBUTED\s+)?QUERY\s+(\w+)", q_code, re.IGNORECASE)
    return m.group(1) if m else fallback


def install_queries(client: TigerGraphClient, dry_run: bool = False, only: list[str] | None = None) -> None:
    """Create all queries in graph/queries/*.gsql, then compile them in one INSTALL call."""
    if not QUERIES_DIR.exists():
        logger.info("No queries directory found at %s", QUERIES_DIR)
        return

    query_files = sorted(QUERIES_DIR.glob("*.gsql"))
    if not query_files:
        logger.info("No .gsql query files found in %s", QUERIES_DIR)
        return

    graphname = client.settings.tg_graphname or "GraphRAG"
    created: list[str] = []
    for qfile in query_files:
        with open(qfile, encoding="utf-8") as f:
            q_code = f.read()
        name = _query_name(q_code, qfile.stem)
        if only and name not in only:
            continue

        logger.info("Creating query %s (from %s)...", name, qfile.name)
        if dry_run:
            continue
        try:
            res = client.conn.gsql(f"USE GRAPH {graphname}\n{q_code}")
            if "error" in str(res).lower() or "fail" in str(res).lower():
                logger.error("Create %s reported a problem:\n%s", name, res)
                continue
            created.append(name)
        except Exception as e:
            logger.error("Failed to create query %s: %s", name, e)

    if dry_run or not created:
        logger.info("Nothing to install (dry_run=%s, created=%s)", dry_run, created)
        return

    logger.info("Installing %d queries: %s", len(created), ", ".join(created))
    res = client.conn.gsql(f"USE GRAPH {graphname}\nINSTALL QUERY {', '.join(created)}")
    logger.info("Install result:\n%s", res)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install TigerGraph schema and queries.")
    parser.add_argument("--dry-run", action="store_true", help="Print DDL without executing")
    parser.add_argument("--queries-only", action="store_true", help="Install queries only")
    parser.add_argument("--only", nargs="*", default=None, help="Install only these query names")
    args = parser.parse_args()

    settings = get_tg_settings()
    client = TigerGraphClient(settings=settings)

    if not args.queries_only:
        install_schema(client, dry_run=args.dry_run)
    install_queries(client, dry_run=args.dry_run, only=args.only)


if __name__ == "__main__":
    main()
