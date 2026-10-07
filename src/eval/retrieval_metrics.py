"""
Retrieval evaluation metrics: Recall@k, Precision@k, MRR.

Evaluates retrieved chunks against gold_doc_ids for a question.
A chunk is relevant if its parent document is in gold_doc_ids.
"""

from __future__ import annotations

from typing import Sequence


def get_doc_id_from_chunk(chunk_id: str, chunk_to_doc: dict[str, str] | None = None) -> str:
    """Extract doc_id from chunk mapping or chunk ID prefix convention (doc_id_c001 or doc_id_chunk_0)."""
    if chunk_to_doc and chunk_id in chunk_to_doc:
        return chunk_to_doc[chunk_id]
    if "_c" in chunk_id:
        return chunk_id.rsplit("_c", 1)[0]
    if "_chunk_" in chunk_id:
        return chunk_id.rsplit("_chunk_", 1)[0]
    return chunk_id


def recall_at_k(
    retrieved_chunk_ids: Sequence[str],
    gold_doc_ids: Sequence[str],
    chunk_to_doc: dict[str, str] | None = None,
    k: int | None = None,
) -> float:
    """
    Calculate Recall@k: fraction of gold documents covered by top-k retrieved chunks.
    """
    if not gold_doc_ids:
        return 1.0

    target_chunks = retrieved_chunk_ids[:k] if k is not None else retrieved_chunk_ids
    retrieved_docs = {get_doc_id_from_chunk(cid, chunk_to_doc) for cid in target_chunks}
    gold_set = set(gold_doc_ids)

    hits = len(retrieved_docs & gold_set)
    return hits / len(gold_set)


def precision_at_k(
    retrieved_chunk_ids: Sequence[str],
    gold_doc_ids: Sequence[str],
    chunk_to_doc: dict[str, str] | None = None,
    k: int | None = None,
) -> float:
    """
    Calculate Precision@k: fraction of top-k retrieved chunks that belong to a gold document.
    """
    target_chunks = retrieved_chunk_ids[:k] if k is not None else retrieved_chunk_ids
    if not target_chunks:
        return 0.0

    gold_set = set(gold_doc_ids)
    hits = sum(1 for cid in target_chunks if get_doc_id_from_chunk(cid, chunk_to_doc) in gold_set)
    return hits / len(target_chunks)


def mrr_at_k(
    retrieved_chunk_ids: Sequence[str],
    gold_doc_ids: Sequence[str],
    chunk_to_doc: dict[str, str] | None = None,
    k: int | None = None,
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR): 1 / rank of the first relevant chunk in top-k.
    Returns 0.0 if no relevant chunk is retrieved in top-k.
    """
    if not gold_doc_ids or not retrieved_chunk_ids:
        return 0.0

    target_chunks = retrieved_chunk_ids[:k] if k is not None else retrieved_chunk_ids
    gold_set = set(gold_doc_ids)

    for rank, cid in enumerate(target_chunks, start=1):
        if get_doc_id_from_chunk(cid, chunk_to_doc) in gold_set:
            return 1.0 / rank

    return 0.0


def evaluate_retrieval(
    retrieved_chunk_ids: Sequence[str],
    gold_doc_ids: Sequence[str],
    chunk_to_doc: dict[str, str] | None = None,
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, float]:
    """
    Compute a complete set of retrieval metrics for a question.
    """
    metrics: dict[str, float] = {}
    for k in ks:
        metrics[f"recall@{k}"] = round(recall_at_k(retrieved_chunk_ids, gold_doc_ids, chunk_to_doc, k=k), 4)
        metrics[f"precision@{k}"] = round(precision_at_k(retrieved_chunk_ids, gold_doc_ids, chunk_to_doc, k=k), 4)

    metrics["mrr"] = round(mrr_at_k(retrieved_chunk_ids, gold_doc_ids, chunk_to_doc), 4)
    return metrics
