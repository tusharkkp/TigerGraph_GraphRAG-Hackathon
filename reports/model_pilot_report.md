# Model Reliability Pilot & Quota Projection Report

**Date:** 2026-10-02  
**Evaluation Scope:** 10 validation questions (`val` split: pub-010, pub-011, pub-014, pub-023, pub-027, pub-028, pub-034, pub-039, pub-042, pub-044).  
**Task:** Pydantic structured output (`OrchestratorAction`) evaluation for QA planning.

---

## 1. Reliability & Performance Comparison

| Model | Schema Pass Rate | Schema Repairs | Mean Latency | Avg Input Tokens | Avg Output Tokens | Status / Availability |
|---|---|---|---|---|---|---|
| **Gemini Flash-Lite 3.1 Preview** (`gemini-3.1-flash-lite-preview`) | **10/10 (100%)** | **0** | **3,269 ms** | 174 | 138 | **Pass** (Handled 503 spike via exponential backoff; completed all 10) |
| **Gemini 2.5 Flash** (`gemini-2.5-flash`) | 1/10 (Incomplete) | N/A | 2,457 ms | 173 | 274 | **Blocked by Daily Quota** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier` = 20) |

---

## 2. Key Empirical Findings

1. **Daily Quota Ceiling on Gemini 2.5 Flash:**
   - The Gemini Developer API enforces a strict daily limit of **20 requests per day** on `gemini-2.5-flash` for free-tier projects (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit: 20).
   - This hard ceiling makes `gemini-2.5-flash` unviable for running the 100-question benchmark (dev 60 + val 20 + test 20) or the 50-question hidden set.
2. **Schema Adherence on Gemini 3.1 Flash-Lite Preview:**
   - Produced 100% valid JSON matching `OrchestratorAction` on the first attempt across all 10 questions.
   - Zero validation errors, zero repairs needed.
   - Average token consumption is modest (~174 prompt, ~138 candidates).
3. **Spike Resilience:**
   - `gemini-3.1-flash-lite-preview` encountered a temporary 503 Service Unavailable on `pub-023`. The `LLMGateway` exponential backoff and jitter retried after 1.04s and succeeded immediately with zero manual intervention.

---

## 3. Quota & Token Budget Projections

Estimated call volume for complete benchmark execution:

- **P1 (Vector RAG Baseline):** 100 calls (1 per question)
- **P2 (GraphRAG Baseline):** 100 calls (1 per question)
- **P3 (Agentic GraphRAG):** ~350 calls (~3.5 calls/question average)
- **Hidden-50 Evaluation:** 50 calls
- **Stage 2 LLM Judge (`gemini-2.5-pro`):** ~40 calls (only on Stage 1 mismatches)
- **Total QA LLM Calls:** ~600 calls across all pipelines

| Role | Model | Calls | Tokens / Call | Total Est. Tokens | Quota Feasibility |
|---|---|---|---|---|---|
| QA Answer & Orchestration | `gemini-3.1-flash-lite-preview` | ~600 | ~350 | ~210,000 | **Viable** |
| Mismatch Judge (Stage 2) | `gemini-2.5-pro` | ~40 | ~400 | ~16,000 | **Viable** |

---

## 4. Locked Configuration Decision

**Decision:** Lock `gemini-3.1-flash-lite-preview` as the primary model for `answer`, `orchestrator`, `agent`, and `extract` in `configs/models.yaml`.  
**Judge Model:** Keep `gemini-2.5-pro` for `judge` role (evaluating Stage 2 mismatches only).
