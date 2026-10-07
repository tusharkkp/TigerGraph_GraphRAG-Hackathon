# Benchmark Report: P3 (val)

**Generated:** 2026-10-07T18:29:57.007664+00:00
**Embedding Model:** `BAAI/bge-base-en-v1.5`

## Overall Performance

- **Total Questions:** 20
- **Accuracy (PASS Rate):** 55.0%
- **Stage 1 Match Rate:** 50.0% (evaluated without LLM judge)
- **Recall@1:** 12.6%
- **Recall@5:** 39.5%
- **MRR:** 0.471
- **Mean Latency:** 16628 ms
- **Avg Tokens / Question:** 8964

## Breakdown by Question Type

| Question Type | Total | Passes | Accuracy % |
|---|---|---|---|
| `aggregation` | 4 | 2 | **50.0%** |
| `lookup` | 4 | 4 | **100.0%** |
| `multi_hop` | 6 | 1 | **16.7%** |
| `superlative` | 2 | 1 | **50.0%** |
| `temporal` | 4 | 3 | **75.0%** |
