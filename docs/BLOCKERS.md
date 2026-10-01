# Blockers

## Active

### B-004: Hidden-50 submission format unconfirmed
**Status:** LOW — defaulting to JSONL with our schema  
**Details:** The guidebook doesn't specify an exact submission format. We default to `question_id, answer, tokens{...}, trace[...], citations[...]`.  
**Action needed:** Owner to confirm on Discord if there's a required format

## Resolved

### B-001: Missing GEMINI_API_KEY
**Resolved:** 2026-10-01  
**Resolution:** Live Gemini API key configured and tested; `gemini-2.5-flash` and `gemini-embedding-001` (768-dim) verified via `tests/integration/test_gemini_smoke.py`.

### B-002: TG_HOST is web console URL, not REST endpoint
**Resolved:** 2026-10-01  
**Resolution:** Updated with live cluster REST endpoint `https://tg-6129cb39-c617-4f5f-b422-bb9ea37c948c.tg-2635877100.i.tgcloud.io`.

### B-003: TigerGraph Savanna Authentication
**Resolved:** 2026-10-01  
**Resolution:** Generated valid JWT `TG_TOKEN` from TigerGraph secret via `POST /gsql/v1/tokens` and configured Bearer auth in `src/graph/client.py`; verified live connection to TigerGraph 4.2.5 via `tests/integration/test_tigergraph_smoke.py`.

