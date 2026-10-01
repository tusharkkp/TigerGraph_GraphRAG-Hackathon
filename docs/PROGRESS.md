# Progress Log

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
- [x] 53/53 unit tests passing offline in ~1.5s (`tests/unit/`)

### In Progress
- [ ] Phase 0 TigerGraph Savanna live gate: pending `TG_TOKEN` from user in `.env`
- [ ] Schema deployment to Savanna via `python -m src.graph.install`

### Next
- [ ] Run `make test-integration` once user adds `TG_TOKEN` to `.env`
- [ ] Deploy schema to Savanna (`python -m src.graph.install`)
- [ ] Run test ingestion on small slice (`python -m src.ingestion.pipeline --limit 5`)
- [ ] Begin Phase 2: RAG and GraphRAG baseline pipelines

### Numbers
- Corpus: 2,951 docs, ~5.5M tokens, ~22 MB
- Questions: 100 public (5 types), 50 hidden
- Estimated ingestion LLM calls: ~8,853 (entity extraction) + ~13,853 (embeddings)

### Blockers
See [BLOCKERS.md](BLOCKERS.md)
