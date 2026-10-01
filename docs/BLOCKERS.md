# Blockers

## Active

### B-005: Vector Attribute vs LIST<FLOAT> on Savanna
**Status:** ACTIVE — Recommended default defined  
**Details:** Existing `DocumentChunk` schema has `embedding LIST<FLOAT>`, while native TigerGraph 4.2.5 HNSW requires `ADD VECTOR ATTRIBUTE vec_emb(DIMENSION=768, METRIC="COSINE")` for `vectorSearch()` syntax.  
**Recommended Default:** Execute an additive schema change job adding `VECTOR ATTRIBUTE vec_emb` to `DocumentChunk` so both native GSQL `vectorSearch()` and existing REST upserts operate seamlessly.

### B-006: Team Medalist String Concatenation in Wikipedia Infoboxes
**Status:** ACTIVE — Recommended default defined  
**Details:** In Wikipedia infobox event templates for team events, athlete names are occasionally concatenated without spaces (e.g., `Rudolf DombiRoland Kökény` in K-2, or `Erik LesserDaniel BöhmArnd PeifferSimon Schempp` in relay).  
**Recommended Default:** The structured parser applies regex-based camelCase boundary splitting (`(?<=[a-z\u00e0-\u017f])(?=[A-Z])`) to extract individual athletes, while storing the raw concatenated string in entity aliases to guarantee deterministic matches against unspaced gold answers.

## Resolved

### B-004: Hidden-50 submission format unconfirmed
**Resolved:** 2026-10-02  
**Resolution:** Confirmed via `docs/round_1.txt` lines 62 & 72. Required submission is a separate JSON/CSV file in repo with the 50 hidden questions: answers generated, tokens used, citations, and agentic trace. Standardized to `reports/hidden50_submission.jsonl` matching `PipelineResult`.

### B-001: Missing GEMINI_API_KEY
**Resolved:** 2026-10-01  
**Resolution:** Live Gemini API key configured and tested; `gemini-2.5-flash` and `gemini-embedding-001` (768-dim) verified via `tests/integration/test_gemini_smoke.py`.

### B-002: TG_HOST is web console URL, not REST endpoint
**Resolved:** 2026-10-01  
**Resolution:** Updated with live cluster REST endpoint `https://tg-6129cb39-c617-4f5f-b422-bb9ea37c948c.tg-2635877100.i.tgcloud.io`.

### B-003: TigerGraph Savanna Authentication
**Resolved:** 2026-10-01  
**Resolution:** Generated valid JWT `TG_TOKEN` from TigerGraph secret via `POST /gsql/v1/tokens` and configured Bearer auth in `src/graph/client.py`; verified live connection to TigerGraph 4.2.5 via `tests/integration/test_tigergraph_smoke.py`.

