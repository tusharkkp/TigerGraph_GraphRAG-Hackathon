# Benchmark Report: P1 (all100)

**Generated:** 2026-10-07T17:51:24.056013+00:00
**Embedding Model:** `BAAI/bge-base-en-v1.5`

## Overall Performance

- **Total Questions:** 100
- **Accuracy (PASS Rate):** 60.0%
- **Stage 1 Match Rate:** 54.0% (evaluated without LLM judge)
- **Recall@1:** 33.8%
- **Recall@5:** 62.6%
- **MRR:** 0.75
- **Mean Latency:** 9890 ms
- **Avg Tokens / Question:** 2941

## Breakdown by Question Type

| Question Type | Total | Passes | Accuracy % |
|---|---|---|---|
| `aggregation` | 21 | 0 | **0.0%** |
| `lookup` | 19 | 19 | **100.0%** |
| `multi_hop` | 28 | 13 | **46.4%** |
| `superlative` | 10 | 6 | **60.0%** |
| `temporal` | 22 | 22 | **100.0%** |
