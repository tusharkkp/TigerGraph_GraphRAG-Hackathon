"""
End-to-end ingestion pipeline: corpus -> chunks -> extraction -> embeddings -> TigerGraph.

Designed for idempotency, resumability with checkpoints, and detailed statistics reporting.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
from typing import Any

from src.config import DATA_DIR, PROJECT_ROOT, REPORTS_DIR, get_tg_settings
from src.graph.client import TigerGraphClient
from src.ingestion.chunker import TextChunker
from src.ingestion.extractor import EntityRelationshipExtractor
from src.llm.embeddings import EmbeddingsService
from src.llm.gateway import LLMGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = PROJECT_ROOT / "data" / "processed" / "ingestion_checkpoint.json"


class IngestionPipeline:
    """Manages the full document-to-graph loading pipeline."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        tg_client: TigerGraphClient | None = None,
        embeddings_service: EmbeddingsService | None = None,
        chunker: TextChunker | None = None,
        checkpoint_path: Path | None = None,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.tg_client = tg_client or TigerGraphClient(settings=get_tg_settings())
        self.embeddings = embeddings_service or EmbeddingsService(gateway=self.gateway)
        self.chunker = chunker or TextChunker()
        self.extractor = EntityRelationshipExtractor(gateway=self.gateway)
        self.checkpoint_path = checkpoint_path or CHECKPOINT_FILE

    def load_checkpoint(self) -> set[str]:
        """Load set of already-processed doc_ids."""
        if not self.checkpoint_path.exists():
            return set()
        try:
            with open(self.checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("processed_docs", []))
        except Exception as e:
            logger.warning("Could not read checkpoint file: %s", e)
            return set()

    def save_checkpoint(self, processed_docs: set[str]) -> None:
        """Persist processed doc_ids."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({"processed_docs": sorted(processed_docs)}, f, indent=2)
        except Exception as e:
            logger.warning("Could not write checkpoint file: %s", e)

    def run(
        self,
        corpus_path: Path | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the ingestion pipeline.

        Args:
            corpus_path: Path to corpus.jsonl.
            limit: Maximum documents to process.
            dry_run: If True, chunk and extract but skip TigerGraph upserts.
        """
        c_path = corpus_path or (DATA_DIR / "corpus" / "corpus.jsonl")
        if not c_path.exists():
            raise FileNotFoundError(f"Corpus file not found: {c_path}")

        processed_docs = self.load_checkpoint()
        logger.info("Loaded %d previously processed doc IDs from checkpoint.", len(processed_docs))

        # Stats counters
        stats = {
            "docs_processed": 0,
            "chunks_created": 0,
            "entities_extracted": 0,
            "relations_extracted": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "embeddings_generated": 0,
            "sample_relations": [],
        }

        docs_to_process: list[dict[str, Any]] = []
        with open(c_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                if doc["doc_id"] not in processed_docs:
                    docs_to_process.append(doc)
                    if limit and len(docs_to_process) >= limit:
                        break

        logger.info("Identified %d new documents to ingest.", len(docs_to_process))

        for idx, doc in enumerate(docs_to_process):
            doc_id = doc["doc_id"]
            logger.info("[%d/%d] Ingesting %s: %s", idx + 1, len(docs_to_process), doc_id, doc.get("title", ""))

            # 1. Chunk document
            chunks = self.chunker.chunk_document(doc)
            sibling_edges = self.chunker.get_sibling_edges(chunks)
            stats["chunks_created"] += len(chunks)

            # 2. Embed chunks
            chunk_texts = [c["text"] for c in chunks]
            embeddings_res = self.embeddings.embed_documents(chunk_texts)
            stats["embeddings_generated"] += len(embeddings_res.embeddings)
            stats["tokens_in"] += embeddings_res.tokens_used

            # Attach embeddings to chunks
            for i, c in enumerate(chunks):
                c["embedding"] = embeddings_res.embeddings[i] if i < len(embeddings_res.embeddings) else []

            # 3. Extract entities and relationships
            all_entities: list[tuple[str, dict[str, Any]]] = []
            all_mentions: list[tuple[str, str, str, str, str, dict[str, Any]]] = []
            all_relates: list[tuple[str, str, str, str, str, dict[str, Any]]] = []

            for chunk in chunks:
                extraction = self.extractor.extract_from_chunk(chunk)
                elements = self.extractor.build_graph_elements(chunk, extraction)

                stats["tokens_in"] += extraction.tokens_in
                stats["tokens_out"] += extraction.tokens_out

                all_entities.extend(elements["entities"])
                all_mentions.extend(elements["mentions_edges"])
                all_relates.extend(elements["relates_edges"])

                # Keep a sample of relations for spot checks
                for r in extraction.relations:
                    if len(stats["sample_relations"]) < 10 and r.quote:
                        stats["sample_relations"].append({
                            "source": r.source,
                            "relation": r.relationship_type,
                            "target": r.target,
                            "quote": r.quote,
                            "doc_id": doc_id,
                        })

            stats["entities_extracted"] += len(all_entities)
            stats["relations_extracted"] += len(all_relates)

            # 4. Upsert into TigerGraph
            if not dry_run:
                # Upsert Document vertex
                doc_attrs = {
                    "title": doc.get("title", ""),
                    "url": doc.get("url", ""),
                    "wikidata_qid": doc.get("wikidata_qid", ""),
                    "approx_tokens": doc.get("approx_tokens", 0),
                }
                self.tg_client.upsert_vertex("Document", doc_id, doc_attrs)

                # Upsert DocumentChunk vertices
                chunk_tuples = [
                    (
                        c["chunk_id"],
                        {
                            "chunk_index": c["chunk_index"],
                            "text": c["text"],
                            "approx_tokens": c["approx_tokens"],
                            "embedding": c.get("embedding", []),
                        },
                    )
                    for c in chunks
                ]
                self.tg_client.upsert_vertices("DocumentChunk", chunk_tuples)

                # Upsert HAS_CHUNK edges
                has_chunk_edges = [
                    ("Document", doc_id, "HAS_CHUNK", "DocumentChunk", c["chunk_id"], {})
                    for c in chunks
                ]
                self.tg_client.upsert_edges(has_chunk_edges)

                # Upsert SIBLING_OF edges
                if sibling_edges:
                    sib_tuples = [
                        ("DocumentChunk", c1, "SIBLING_OF", "DocumentChunk", c2, attrs)
                        for c1, c2, attrs in sibling_edges
                    ]
                    self.tg_client.upsert_edges(sib_tuples)

                # Upsert Entity vertices
                if all_entities:
                    self.tg_client.upsert_vertices("Entity", all_entities)

                # Upsert MENTIONS and RELATES_TO edges
                if all_mentions:
                    self.tg_client.upsert_edges(all_mentions)
                if all_relates:
                    self.tg_client.upsert_edges(all_relates)

            processed_docs.add(doc_id)
            stats["docs_processed"] += 1

            # Save checkpoint every 5 docs
            if stats["docs_processed"] % 5 == 0:
                self.save_checkpoint(processed_docs)

        # Final checkpoint save
        self.save_checkpoint(processed_docs)
        self._write_report(stats)
        return stats

    def _write_report(self, stats: dict[str, Any]) -> None:
        """Write ingestion statistics to reports/ingestion_stats.json and markdown."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        stats_file = REPORTS_DIR / "ingestion_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        md_file = REPORTS_DIR / "ingestion_stats.md"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        total_tokens = stats.get("tokens_in", 0) + stats.get("tokens_out", 0)
        md_content = f"""# Ingestion Statistics Report

**Generated:** {now}

## Summary
- **Documents Processed:** {stats['docs_processed']}
- **Chunks Created:** {stats['chunks_created']}
- **Embeddings Generated:** {stats['embeddings_generated']}
- **Entities Discovered:** {stats['entities_extracted']}
- **Relations Discovered:** {stats['relations_extracted']}
- **Input Tokens:** {stats['tokens_in']:,}
- **Output Tokens:** {stats['tokens_out']:,}
- **Total Tokens:** {total_tokens:,}

## Sample Extracted Relations (Spot Check)
| Source | Relation | Target | Quote |
|---|---|---|---|
"""
        for s in stats.get("sample_relations", []):
            md_content += f"| {s['source']} | {s['relation']} | {s['target']} | \"{s['quote'][:100]}\" |\n"

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Saved ingestion stats report to %s", md_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Olympic corpus into TigerGraph Savanna.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to ingest")
    parser.add_argument("--dry-run", action="store_true", help="Chunk and extract without upserting to TigerGraph")
    args = parser.parse_args()

    pipeline = IngestionPipeline()
    stats = pipeline.run(limit=args.limit, dry_run=args.dry_run)
    print("\nIngestion Complete!")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
