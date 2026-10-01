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

### In Progress
- [ ] Phase 0 gate: smoke tests pending (need GEMINI_API_KEY + correct TG_HOST)

### Next
- [ ] Get credentials from owner (Gemini key, TG REST endpoint, TG username)
- [ ] Run Savanna + Gemini smoke tests
- [ ] Begin Phase 1: LLM Gateway → TG Client → Schema → Ingestion

### Numbers
- Corpus: 2,951 docs, ~5.5M tokens, ~22 MB
- Questions: 100 public (5 types), 50 hidden
- Estimated ingestion LLM calls: ~8,853 (entity extraction) + ~13,853 (embeddings)

### Blockers
See [BLOCKERS.md](BLOCKERS.md)
