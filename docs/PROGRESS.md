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
- [x] Added unit tests for Cache and Gateway (42/42 total unit tests passing)
- [x] Added integration smoke tests (`tests/integration/test_gemini_smoke.py`, `tests/integration/test_tigergraph_smoke.py`)

### In Progress
- [ ] Phase 0 gate closure: live smoke tests pending credentials (`GEMINI_API_KEY` and REST endpoint `TG_HOST`)
- [ ] Phase 1 TigerGraph client wrapper (`src/graph/client.py`) and schema installer

### Next
- [ ] Receive credentials from owner (Gemini API key, Savanna REST endpoint, TG username)
- [ ] Execute `make test-integration` for live smoke verification
- [ ] Build `src/graph/client.py` and `src/graph/install.py`
- [ ] Implement ingestion pipeline (`src/ingestion/chunking.py`, `src/ingestion/extraction.py`, `src/ingestion/loader.py`)

### Numbers
- Corpus: 2,951 docs, ~5.5M tokens, ~22 MB
- Questions: 100 public (5 types), 50 hidden
- Estimated ingestion LLM calls: ~8,853 (entity extraction) + ~13,853 (embeddings)

### Blockers
See [BLOCKERS.md](BLOCKERS.md)
