# ADR-007: Local Embedding Provider with BGE-base-en-v1.5

## Status
Accepted (2026-10-02)

## Context
Full corpus ingestion (2,951 documents, ~16,200 chunks) was blocked after ingesting 55 documents due to Gemini API Free Tier quota exhaustion. Gemini embedding endpoints (`gemini-embedding-001` / `text-embedding-004`) enforce strict daily limits (1,500 RPD) and rate limits that prevent continuous bulk ingestion.

The system requires an embedding model that:
1. Operates completely locally without API quota constraints.
2. Emits exactly 768-dimensional vectors to preserve the existing TigerGraph Savanna schema (`vec_emb` attribute on `DocumentChunk` and the native HNSW vector index).
3. Executes efficiently on multi-core CPU with fast throughput (>2 chunks/sec).
4. Maintains high retrieval recall on passage search tasks.

## Decision
1. **Embedding Provider Abstraction:** Introduce `EmbeddingProvider` in `src/llm/embeddings.py` with `FastEmbedProvider` as the local default and `GeminiEmbeddingProvider` as the remote fallback.
2. **Selected Model:** `BAAI/bge-base-en-v1.5` running via `fastembed` (ONNX runtime, quantized `Qdrant/bge-base-en-v1.5-onnx-Q`).
   - Dimension: 768
   - Pinned Model: `BAAI/bge-base-en-v1.5`
   - Pinned Revision: `main` (commit `199291fdd1aa89faf9c20b722dc72ad5e17aa0d0`)
3. **Prefixes:**
   - Queries: `"Represent this sentence for searching relevant passages: "`
   - Documents: `""` (no prefix)
4. **Sequence Length vs Chunk Size:**
   - Model max sequence length: 512 tokens.
   - Corpus chunk distribution (sampled 885 chunks): Min: 27 tokens, Max: 1,079 tokens, Mean: 449.4 tokens.
   - 98.0% of chunks are within the 512-token limit.
   - Chunks exceeding 512 tokens (2.0%) are deterministically truncated by the ONNX tokenizer.
5. **Unified Embedding Space:** Re-embed all previously ingested chunks with `BAAI/bge-base-en-v1.5` so that all vector comparisons occur in a single, homogeneous vector space.
6. **Provenance Tracking:** The active embedding model name is recorded in `configs/models.yaml`, all evaluation records, JSON summaries, and markdown benchmark reports.

## Benchmark & Empirical Evidence (200 Real Chunks)
A head-to-head CPU benchmark was conducted on 200 real corpus chunks:

| Metric | BAAI/bge-base-en-v1.5 | nomic-ai/nomic-embed-text-v1.5 |
|---|---|---|
| **Dimension** | 768 | 768 |
| **Model Load Time** | 29.3 s | 53.0 s |
| **Time for 200 Chunks** | **83.20 s** | > 500 s |
| **CPU Throughput** | **2.40 chunks/sec** | ~0.38 chunks/sec |
| **Memory Footprint** | **< 500 MB** | ~2.9 GB |
| **Extrapolated Time (~16.2k chunks)** | **~1.87 hours** | > 11.2 hours |

`bge-base-en-v1.5` is ~6.3x faster, uses 1/6th the memory, and completes full corpus ingestion in under 2 hours.

## Consequences
- **Positive:** Ingestion is unblocked; zero external API quota consumed; zero cost; predictable 1.87h completion time.
- **Positive:** Vector index in Savanna requires zero schema migration.
- **Neutral:** Chunks >512 tokens have trailing sentences excluded from embedding, but the chunk text in TigerGraph retains full content for LLM generation context.
