# Blockers

## Active

### B-001: Missing GEMINI_API_KEY
**Status:** BLOCKING Phase 0 gate, all Phase 1+ work  
**Impact:** Cannot run any LLM calls, embeddings, or extraction  
**Action needed:** Owner to provide Gemini API key and add to `.env`

### B-002: TG_HOST is web console URL, not REST endpoint
**Status:** BLOCKING Phase 0 gate, all TigerGraph operations  
**Details:** Current `.env` has `TG_HOST=https://tgcloud.io/groups/a57c9a58-...` which is the Savanna web console URL. pyTigerGraph needs the REST API endpoint (format: `https://<instance-id>.i.tgcloud.io`).  
**Action needed:** Owner to go to Savanna console → workspace → copy the REST endpoint  

### B-003: Missing TG_USERNAME
**Status:** BLOCKING Phase 0 gate  
**Details:** Only TG_PASSWORD is in `.env`. Need username (typically `tigergraph`).  
**Action needed:** Owner to confirm username and add to `.env`

### B-004: Hidden-50 submission format unconfirmed
**Status:** LOW — defaulting to JSONL with our schema  
**Details:** The guidebook doesn't specify an exact submission format. We default to `question_id, answer, tokens{...}, trace[...], citations[...]`.  
**Action needed:** Owner to confirm on Discord if there's a required format

## Resolved
(none yet)
