"""
Schema and query deployment script for TigerGraph Savanna.

Idempotently installs or updates the GraphRAG schema and GSQL queries.
"""

from __future__ import annotations

import argparse
import logging

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
    wrapped_ddl = f"USE GRAPH {graphname}\n{gsql}"
    try:
        res = client.conn.gsql(wrapped_ddl)
        logger.info("Schema deployment result: %s", res)
    except Exception as e:
        logger.error("Schema deployment failed: %s", e)
        raise


def install_queries(client: TigerGraphClient, dry_run: bool = False) -> None:
    """Install all queries found in graph/queries/*.gsql."""
    if not QUERIES_DIR.exists():
        logger.info("No queries directory found at %s", QUERIES_DIR)
        return

    query_files = list(QUERIES_DIR.glob("*.gsql"))
    if not query_files:
        logger.info("No .gsql query files found in %s", QUERIES_DIR)
        return

    graphname = client.settings.tg_graphname or "GraphRAG"
    for qfile in query_files:
        with open(qfile, encoding="utf-8") as f:
            q_code = f.read()

        logger.info("Deploying query from %s...", qfile.name)
        if dry_run:
            logger.info("[Dry Run] Would install query %s", qfile.name)
            continue

        try:
            # Install query via pyTigerGraph or gsql command
            gsql_cmd = f"USE GRAPH {graphname}\n{q_code}\nINSTALL QUERY {qfile.stem}"
            res = client.conn.gsql(gsql_cmd)
            logger.info("Installed %s: %s", qfile.stem, res)
        except Exception as e:
            logger.error("Failed to install query %s: %s", qfile.stem, e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install TigerGraph schema and queries.")
    parser.add_argument("--dry-run", action="store_true", help="Print DDL without executing")
    parser.add_argument("--queries-only", action="store_true", help="Install queries only")
    args = parser.parse_args()

    settings = get_tg_settings()
    client = TigerGraphClient(settings=settings)

    if not args.queries_only:
        install_schema(client, dry_run=args.dry_run)
    install_queries(client, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
