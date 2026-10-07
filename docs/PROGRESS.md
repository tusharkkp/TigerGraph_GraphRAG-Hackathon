# Progress Log

## 2026-10-07 — Current state

### Done
- [x] Full corpus ingested (on secondary machine): 2,951 Document, 13,873 DocumentChunk with 768-d bge-base vectors
- [x] Structured layer: 2,187 Event, 6,220 Athlete, 133 Country, 314 Venue, 42 Sport, 21 Games; 8,415 MEDALIST, 1,383 PREVIOUS/NEXT_EDITION
- [x] Event layer rebuilt with sport-aware, plus-preserving IDs (no collisions)
- [x] All 9 GSQL tools installed (fixed V2 edge-direction syntax + PRINT LIMIT errors in 5 queries)
- [x] Runner import bug fixed; stale 55-doc val checkpoints removed
- [x] Deterministic agentic parts (EntityLinker, EvidenceEvaluator, FakeOrchestrator) + 7 behaviour tests passing

### In Progress
- [ ] P1 / P2 full 100-question baselines (`--split all100`)

### Next
- [ ] P3 live orchestrator + pipeline (LLM planner → GSQL tools, ≤3 LLM calls/q)
- [ ] 3-way benchmark, hidden-50 export + validation, README / demo

---

## 2026-10-01

### Done
- [x] Read all guide files (AGENT.md, SKILLS.md, Automated_Verification_Loops.md, LOOP_INSTRUCTIONS.md)
- [x] Read hackathon guidelines (Problem_Statement.md, hackathon.txt)
- [x] Inspected dataset: 2,951 Olympic Wikipedia docs, 100 public + 50 hidden questions
- [x] Documented question types: multi_hop(28), temporal(22), aggregation(21), lookup(19), superlative(10)
- [x] GraphRAG repo spike → ADR-001 written (reuse schema+GSQL, write our own code)
- [x] Scaffolded repo: all directories, configs, contracts, Makefile, pyproject.toml
- [x] Created data/splits.json (dev 60 / val 20 / test 20, stratified by qtype, seed 42)
- [x] Wrote docs: DECISIONS.md, PROGRESS.md, BLOCKERS.md, ARCHITECTURE.md
- [x] Implemented `src/llm/cache.py` (thread-safe disk cache keyed by SHA-256)
- [x] Implemented `src/llm/gateway.py` (Gemini gateway with exact token accounting, retries on 429/5xx, Pydantic structured output validation + single repair attempt, JSONL logging)
- [x] Implemented `src/llm/embeddings.py` (document and query embedding service)
- [x] Probed live Gemini API: updated `configs/models.yaml` to `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-embedding-001` (768-dim)
- [x] Passed live Gemini integration smoke tests (`tests/integration/test_gemini_smoke.py`)
- [x] Built `src/graph/client.py` (`TigerGraphClient` with token re-auth, batch upserts, query execution)
- [x] Built `src/graph/install.py` (schema and GSQL query deployment)
- [x] Built `src/ingestion/chunker.py` (`TextChunker` with sentence boundary preservation and sibling links)
- [x] Built `src/ingestion/extractor.py` (`EntityRelationshipExtractor` with Olympic domain ontology and canonical IDs)
- [x] Built `src/ingestion/pipeline.py` (resumable ingestion pipeline with checkpoints and stats reporting)
- [x] Acquired valid TigerGraph JWT token and verified live Savanna connectivity (`tests/integration/test_tigergraph_smoke.py`)
- [x] Fixed GSQL syntax in `graph/schema.gsql` (wrapped in `SCHEMA_CHANGE JOB`, corrected `--` to `//`)
- [x] Deployed and verified GraphRAG schema on TigerGraph Savanna (`Document`, `DocumentChunk`, `Entity`, `EntityType`, `RelationshipType`, `Community`, and 7 edge types)
- [x] Verified test ingestion on small slice (`py -3.12 -m src.ingestion.pipeline --limit 5`): 5 docs, 16 chunks, 121 entities, 16 HAS_CHUNK, 245 MENTIONS, 87 RELATES_TO, 11 SIBLING_OF live in Savanna
- [x] Reviewed `docs/round_1.txt` and verified JSON format for hidden-50 submission
- [x] 56/56 tests passing (53 unit tests + 3 live integration tests)

### In Progress
- [ ] Phase 2: Baselines & Evaluation
  - Implement P1 RAG pipeline (`src/pipelines/rag.py`)
  - Implement P2 GraphRAG pipeline (`src/pipelines/graphrag.py`)
  - Install core GSQL retrieval queries in `graph/queries/`
  - Implement LLM judge (`src/eval/judge.py`) & metrics (`src/eval/metrics.py`)
  - Implement evaluation runner (`src/eval/runner.py`)

### Next
- [ ] Run baseline evaluation on dev/val splits
- [ ] Calibrate LLM judge and spot-check 10-20 examples
- [ ] Phase 3: Agentic GraphRAG core harness

### Numbers
- Corpus: 2,951 docs, ~5.5M tokens, ~22 MB
- Questions: 100 public (5 types), 50 hidden
- Live Graph State: 5 Document, 16 DocumentChunk, 121 Entity, 16 HAS_CHUNK, 245 MENTIONS, 87 RELATES_TO, 11 SIBLING_OF
- Test suite: 56 passed (53 unit + 3 integration)

### Blockers
None. Live Savanna and Gemini endpoints verified.
