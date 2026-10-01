"""
Document chunking with sentence boundary preservation and sibling link generation.

Produces deterministic chunk IDs based on doc_id and sequential index,
ensuring 100% idempotent re-runs.
"""

from __future__ import annotations

import re
from typing import Any

from src.config import get_retrieval_config


class TextChunker:
    """Sliding-window chunker with sentence-boundary preservation."""

    def __init__(
        self,
        chunk_size: int | None = None,
        overlap_size: int | None = None,
    ) -> None:
        cfg = get_retrieval_config().get("chunking", {})
        self.chunk_size = chunk_size or int(cfg.get("chunk_size", 500))
        self.overlap_size = overlap_size or int(cfg.get("overlap_size", 75))

        # Approx 4 characters per token
        self.target_chars = self.chunk_size * 4
        self.overlap_chars = self.overlap_size * 4

    @staticmethod
    def _split_into_sentences(text: str) -> list[str]:
        """Split text into sentences/paragraphs while keeping delimiters."""
        # Split on paragraph breaks or sentence terminators followed by whitespace
        parts = re.split(r"(\n\n+|\.\s+|\?\s+|\!\s+)", text)
        sentences: list[str] = []
        for i in range(0, len(parts) - 1, 2):
            sentences.append(parts[i] + parts[i + 1])
        if len(parts) % 2 == 1 and parts[-1]:
            sentences.append(parts[-1])
        return [s for s in sentences if s.strip()]

    def chunk_document(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Split a document into chunks.

        Args:
            doc: Dictionary containing at minimum 'doc_id' and 'text'.
                 Optionally 'title', 'wikidata_qid', 'url'.

        Returns:
            List of chunk dictionaries:
            [{
                'chunk_id': str,
                'doc_id': str,
                'chunk_index': int,
                'text': str,
                'approx_tokens': int,
            }]
        """
        doc_id = str(doc["doc_id"])
        full_text = doc.get("text", "").strip()
        if not full_text:
            return []

        sentences = self._split_into_sentences(full_text)
        if not sentences:
            sentences = [full_text]

        chunks: list[dict[str, Any]] = []
        current_sentences: list[str] = []
        current_len = 0
        chunk_index = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if current_len + sentence_len > self.target_chars and current_sentences:
                # Flush current chunk
                chunk_text = "".join(current_sentences).strip()
                chunks.append({
                    "chunk_id": f"{doc_id}_c{chunk_index:03d}",
                    "doc_id": doc_id,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "approx_tokens": max(1, len(chunk_text) // 4),
                })
                chunk_index += 1

                # Retain overlap sentences from end of current chunk
                overlap_accum: list[str] = []
                overlap_len = 0
                for s in reversed(current_sentences):
                    if overlap_len + len(s) <= self.overlap_chars:
                        overlap_accum.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break
                current_sentences = overlap_accum
                current_len = overlap_len

            current_sentences.append(sentence)
            current_len += sentence_len

        # Flush final chunk
        if current_sentences:
            chunk_text = "".join(current_sentences).strip()
            chunks.append({
                "chunk_id": f"{doc_id}_c{chunk_index:03d}",
                "doc_id": doc_id,
                "chunk_index": chunk_index,
                "text": chunk_text,
                "approx_tokens": max(1, len(chunk_text) // 4),
            })

        return chunks

    @staticmethod
    def get_sibling_edges(chunks: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
        """Generate undirected SIBLING_OF edges between adjacent chunks of the same document."""
        edges: list[tuple[str, str, dict[str, Any]]] = []
        for i in range(len(chunks) - 1):
            c1 = chunks[i]["chunk_id"]
            c2 = chunks[i + 1]["chunk_id"]
            edges.append((c1, c2, {"weight": 1.0}))
        return edges
