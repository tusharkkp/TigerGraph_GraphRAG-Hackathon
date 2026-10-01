# ADR — Architecture Decision Records

## ADR-001: Reuse vs. Build from `tigergraph/graphrag`

**Date:** 2026-10-01  
**Status:** Accepted

### Context
The TigerGraph GraphRAG repo (`github.com/tigergraph/graphrag`) provides a full GraphRAG implementation including schema, GSQL queries, chunkers, extractors, embedders, retrievers, and a web UI. We need to decide what to reuse vs. build from scratch.

### Options
1. **Fork and extend** — use the entire repo as-is, add our agentic layer and benchmark on top
2. **Reuse schema + GSQL only** — take the graph schema and key queries, write everything else ourselves
3. **Build from scratch** — ignore the repo entirely

### Decision
**Option 2: Reuse schema + GSQL, write our own code.**

### Rationale
- The **graph schema** (Document, DocumentChunk, Entity, EntityType, RelationshipType, Community + edges) is well-designed, battle-tested, and matches our needs. Reinventing it wastes time.
- The **GSQL queries** (`Content_Similarity_Vector_Search`, `GraphRAG_Hybrid_Vector_Search`, community queries) are optimised and save days of GSQL debugging.
- Their **LLM/embedding services** are LangChain-based and multi-provider; we need a single Gemini gateway with exact token accounting — incompatible.
- Their **ingestion pipeline** is coupled to their FastAPI server and async job system; we need standalone, idempotent, resumable ingestion.
- Their **retrievers** are useful *patterns* but tightly coupled to their connection proxy; we'll write our own wrappers.
- There is **no agentic harness, evidence ledger, orchestrator, benchmarking pipeline, or evaluation framework** — all must be built.

### Trade-offs
- (+) Schema consistency with the official TigerGraph GraphRAG product
- (+) GSQL queries are pre-optimised for vector + graph hybrid search
- (+) Faster Phase 1 (schema + queries are ready)
- (−) Must understand their schema well enough to extend it (e.g. for temporal facts)
- (−) GSQL queries may need adaptation for our specific traversal patterns
- (−) Can't easily upgrade if the repo changes (but we freeze our reference copy)

### Revisit if
- Their repo adds an agentic framework we could adapt
- Schema proves insufficient for temporal reasoning (need to extend)
