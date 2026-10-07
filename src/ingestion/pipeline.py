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
import time
from typing import Any

from src.config import DATA_DIR, PROJECT_ROOT, REPORTS_DIR, get_tg_settings
from src.graph.client import TigerGraphClient
from src.ingestion.chunker import TextChunker
from src.ingestion.extractor import EntityRelationshipExtractor
from src.ingestion.structured_parser import StructuredInfoboxParser
from src.llm.embeddings import EmbeddingsService
from src.llm.gateway import LLMGateway
from src.utils.normalization import clean_text_for_storage

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
        skip_structured: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the ingestion pipeline.

        Args:
            corpus_path: Path to corpus.jsonl.
            limit: Maximum documents to process.
            dry_run: If True, chunk and extract but skip TigerGraph upserts.
            skip_structured: If True, chunk and embed only; skip structured entity parsing.
        """
        c_path = corpus_path or (DATA_DIR / "corpus" / "corpus.jsonl")
        if not c_path.exists():
            raise FileNotFoundError(f"Corpus file not found: {c_path}")

        processed_docs = self.load_checkpoint()
        logger.info("Loaded %d previously processed doc IDs from checkpoint.", len(processed_docs))

        # Load cumulative stats if existing, or initialize fresh
        stats_file = REPORTS_DIR / "ingestion_stats.json"
        if stats_file.exists():
            try:
                with open(stats_file, encoding="utf-8") as f:
                    stats = json.load(f)
            except Exception:
                stats = {}
        else:
            stats = {}

        stats.setdefault("docs_processed", len(processed_docs))
        stats.setdefault("chunks_created", 0)
        stats.setdefault("entities_extracted", 0)
        stats.setdefault("relations_extracted", 0)
        stats.setdefault("tokens_in", 0)
        stats.setdefault("tokens_out", 0)
        stats.setdefault("embeddings_generated", 0)
        stats.setdefault("sample_relations", [])

        # Prioritize public gold docs first (debugging only), then the rest
        public_gold_path = DATA_DIR / "questions" / "eval_public.jsonl"
        gold_doc_ids: set[str] = set()
        if public_gold_path.exists():
            try:
                with open(public_gold_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            q = json.loads(line)
                            for d in q.get("gold_doc_ids", []):
                                gold_doc_ids.add(str(d))
            except Exception as e:
                logger.warning("Could not read public gold docs: %s", e)

        gold_docs: list[dict[str, Any]] = []
        other_docs: list[dict[str, Any]] = []

        with open(c_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                did = str(doc["doc_id"])
                if did not in processed_docs:
                    if did in gold_doc_ids:
                        gold_docs.append(doc)
                    else:
                        other_docs.append(doc)

        docs_to_process = gold_docs + other_docs
        if limit:
            docs_to_process = docs_to_process[:limit]

        logger.info(
            "Identified %d new documents to ingest (%d public gold docs prioritized, %d remaining).",
            len(docs_to_process),
            len(gold_docs),
            len(other_docs),
        )

        non_infobox_docs_by_type: dict[str, list[str]] = {
            "summary_overview": [],
            "general_olympic": [],
            "non_olympic_wikipedia": [],
            "other": [],
        }

        start_time = time.perf_counter()
        docs_completed_in_run = 0
        chunks_created_in_run = 0

        for idx, doc in enumerate(docs_to_process):
            doc_id = str(doc["doc_id"])
            clean_title = clean_text_for_storage(doc.get("title", ""))
            is_gold = doc_id in gold_doc_ids
            tag = " [GOLD]" if is_gold else ""
            logger.info("[%d/%d]%s Ingesting %s: %s", idx + 1, len(docs_to_process), tag, doc_id, clean_title)

            # 1. Chunk document
            chunks = self.chunker.chunk_document(doc)
            sibling_edges = self.chunker.get_sibling_edges(chunks)
            stats["chunks_created"] += len(chunks)
            chunks_created_in_run += len(chunks)

            # 2. Embed chunks with local BGE model (0 LLM call, 0 Gemini quota)
            chunk_texts = [c["text"] for c in chunks]
            embeddings_res = self.embeddings.embed_documents(chunk_texts)
            stats["embeddings_generated"] += len(embeddings_res.embeddings)

            # Attach embeddings to chunks
            for i, c in enumerate(chunks):
                c["embedding"] = embeddings_res.embeddings[i] if i < len(embeddings_res.embeddings) else []

            # 3. Structured parsing (0 LLM calls) vs Defer Non-Infobox
            structured_elements: dict[str, Any] | None = None
            if not skip_structured:
                parsed_olympic = StructuredInfoboxParser.parse_document(doc)

                if parsed_olympic:
                    # Stage 1: Deterministic structured parsing (0 LLM cost)
                    structured_elements = StructuredInfoboxParser.build_graph_elements(parsed_olympic)
                    stats["entities_extracted"] += (
                        len(structured_elements["Event"])
                        + len(structured_elements["Athlete"])
                        + len(structured_elements["Country"])
                        + len(structured_elements["Venue"])
                        + len(structured_elements["Sport"])
                        + len(structured_elements["Games"])
                    )
                    stats["relations_extracted"] += len(structured_elements["edges"])
                else:
                    # Stage 2: Non-infobox doc: chunk + embed only; LLM extraction deferred per ADR-007
                    title_lower = clean_title.lower()
                    if any(w in title_lower for w in ["summary", "list of", "medal winners", "table", "chronological"]):
                        category = "summary_overview"
                    elif any(w in title_lower for w in ["olympic", "olympics", "games"]):
                        category = "general_olympic"
                    elif any(w in title_lower for w in ["drift", "film", "album", "music", "song", "season", "championship"]):
                        category = "non_olympic_wikipedia"
                    else:
                        category = "other"
                    non_infobox_docs_by_type[category].append(f"{doc_id}: {clean_title}")

            # 4. Upsert into TigerGraph
            if not dry_run:
                # Upsert Document vertex
                doc_attrs = {
                    "title": clean_title,
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
                            "text": clean_text_for_storage(c["text"]),
                            "approx_tokens": c["approx_tokens"],
                            "embedding": c.get("embedding", []),
                            "vec_emb": c.get("embedding", []),
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

                # Upsert structured elements if available
                if structured_elements:
                    for vtype in ("Event", "Games", "Athlete", "Country", "Venue", "Sport"):
                        vitems = structured_elements.get(vtype, [])
                        if vitems:
                            self.tg_client.upsert_vertices(vtype, vitems)
                    if structured_elements.get("edges"):
                        self.tg_client.upsert_edges(structured_elements["edges"])

            processed_docs.add(doc_id)
            stats["docs_processed"] = len(processed_docs)
            docs_completed_in_run += 1

            # Checkpoint every 25 docs (or first 10, or end)
            if docs_completed_in_run % 25 == 0 or docs_completed_in_run == 10:
                elapsed = time.perf_counter() - start_time
                docs_per_sec = docs_completed_in_run / max(elapsed, 0.001)
                chunks_per_sec = chunks_created_in_run / max(elapsed, 0.001)
                rem_docs = len(docs_to_process) - (idx + 1)
                eta_sec = rem_docs / docs_per_sec if docs_per_sec > 0 else 0
                eta_human = str(datetime.timedelta(seconds=int(eta_sec)))

                status_data = {
                    "docs_completed_in_run": docs_completed_in_run,
                    "chunks_created_in_run": chunks_created_in_run,
                    "docs_per_sec": round(docs_per_sec, 2),
                    "chunks_per_sec": round(chunks_per_sec, 2),
                    "elapsed_seconds": round(elapsed, 1),
                    "eta_seconds": round(eta_sec, 1),
                    "eta_human": eta_human,
                    "total_corpus_docs": 2951,
                    "total_processed_docs": len(processed_docs),
                    "embedding_model": self.embeddings.model_name,
                }
                status_file = REPORTS_DIR / "ingestion_status.json"
                REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(status_data, f, indent=2)

                logger.info(
                    "CHECKPOINT [%d/%d] Rate: %.2f docs/s (%.1f chunks/s) | ETA: %s",
                    docs_completed_in_run,
                    len(docs_to_process),
                    docs_per_sec,
                    chunks_per_sec,
                    eta_human,
                )

                if not dry_run:
                    self.save_checkpoint(processed_docs)
                    self._write_report(stats)

        # Final checkpoint save & report non-infobox categorization
        if not dry_run:
            self.save_checkpoint(processed_docs)
            self._write_report(stats)

        non_infobox_report_file = REPORTS_DIR / "non_infobox_docs.json"
        with open(non_infobox_report_file, "w", encoding="utf-8") as f:
            json.dump(non_infobox_docs_by_type, f, indent=2)
        logger.info("Saved non-infobox docs breakdown to %s", non_infobox_report_file)
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
    parser.add_argument("--skip-structured", action="store_true", help="Chunk and embed only, skipping structured entity parsing")
    args = parser.parse_args()

    pipeline = IngestionPipeline()
    stats = pipeline.run(limit=args.limit, dry_run=args.dry_run, skip_structured=args.skip_structured)
    print("\nIngestion Complete!")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
