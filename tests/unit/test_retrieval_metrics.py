"""Unit tests for retrieval metrics."""

from src.eval.retrieval_metrics import (
    evaluate_retrieval,
    mrr_at_k,
    precision_at_k,
    recall_at_k,
)


def test_recall_at_k():
    chunks = ["docA_chunk_0", "docB_chunk_0", "docC_chunk_0"]
    gold = ["docA", "docB"]

    # top-1 only has docA
    assert recall_at_k(chunks, gold, k=1) == 0.5
    # top-2 has docA and docB
    assert recall_at_k(chunks, gold, k=2) == 1.0
    # top-3 has docA and docB
    assert recall_at_k(chunks, gold, k=3) == 1.0


def test_precision_at_k():
    chunks = ["docA_chunk_0", "docX_chunk_0", "docB_chunk_0"]
    gold = ["docA", "docB"]

    assert precision_at_k(chunks, gold, k=1) == 1.0
    assert precision_at_k(chunks, gold, k=2) == 0.5
    assert round(precision_at_k(chunks, gold, k=3), 2) == 0.67


def test_mrr_at_k():
    chunks_hit_first = ["docA_chunk_0", "docX_chunk_0"]
    chunks_hit_second = ["docX_chunk_0", "docA_chunk_0"]
    chunks_no_hit = ["docX_chunk_0", "docY_chunk_0"]
    gold = ["docA"]

    assert mrr_at_k(chunks_hit_first, gold) == 1.0
    assert mrr_at_k(chunks_hit_second, gold) == 0.5
    assert mrr_at_k(chunks_no_hit, gold) == 0.0


def test_evaluate_retrieval_suite():
    chunks = ["docA_chunk_0", "docB_chunk_0"]
    gold = ["docA"]
    res = evaluate_retrieval(chunks, gold, ks=[1, 3])
    assert res["recall@1"] == 1.0
    assert res["recall@3"] == 1.0
    assert res["mrr"] == 1.0


def test_real_chunk_id_separator():
    from src.eval.retrieval_metrics import get_doc_id_from_chunk

    assert get_doc_id_from_chunk("Q1133610_c005") == "Q1133610"
    assert get_doc_id_from_chunk("Q303623_c000") == "Q303623"
    assert get_doc_id_from_chunk("Q12345_chunk_0") == "Q12345"

    chunks = ["Q1133610_c005", "Q303623_c001"]
    gold = ["Q1133610"]
    assert recall_at_k(chunks, gold, k=1) == 1.0
    assert precision_at_k(chunks, gold, k=1) == 1.0
    assert mrr_at_k(chunks, gold) == 1.0

