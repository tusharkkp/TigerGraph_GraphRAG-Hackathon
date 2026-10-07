# ADR-008: Evaluation Judge Model Reconciliation and Quota Strategy

## Status
Accepted (2026-10-02)

## Context
Earlier planning documents and `model_pilot_report.md` initially proposed using `gemini-2.5-pro` (or `gemini-3.1-pro-preview`) as the evaluation judge while using `gemini-3.1-flash-lite-preview` as the pipeline answer model, following best practices to decouple the evaluation judge from the candidate generator.

However, rigorous quota reproduction and verification on the active Google AI Studio project revealed:
1. `gemini-2.5-pro` returns HTTP 404 `NOT_FOUND` (deprecated/sunset for new users).
2. `gemini-3.1-pro-preview` returns HTTP 429 with `limit: 0` (0 daily free-tier quota allocated to this project).
3. `gemini-2.5-flash` enforces a hard cap of 20 requests per day (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit: 20).
4. `gemini-3-flash-preview` enforces 5 RPM and throws 429 errors on evaluation bursts.
5. Only `gemini-3.1-flash-lite-preview` provides reliable free-tier throughput (15 RPM, 1,500 RPD, 1,000,000 TPM).

## Decision
1. **Reconciled Judge Model:** `configs/models.yaml` is locked to `gemini-3.1-flash-lite-preview` for both `answer` and `judge` under Free Tier operation.
2. **Two-Stage Mitigation of Self-Evaluation Bias:**
   - **Stage 1 (Deterministic):** Resolves factual answers via strict normalized set equality (exact diacritic normalization, team medalist unpacking, number matching). Stage 1 uses ZERO LLM calls, eliminating judge bias for exact matches. The empirical Stage 1 match rate will be measured directly on real pipeline outputs after the 100% baseline runs (rather than relying on prior estimates).
   - **Stage 2 (LLM Fallback):** Invoked only for answers requiring natural language semantic equivalence when Stage 1 does not yield an exact match.
3. **Judge Model Selection Policy (Zero Billing Assumption):**
   - No assumptions about paid or billing activation are made.
   - If quota for `gemini-3-flash-preview` allows (5 RPM / burst availability), `configs/models.yaml` will use `gemini-3-flash-preview` as the independent evaluation judge.
   - If rate limits on `gemini-3-flash-preview` cause 429 failures during evaluation runs, the evaluation judge will fall back to `gemini-3.1-flash-lite-preview` (the same model as the answer generator), with this self-evaluation limitation explicitly documented in `reports/findings.md` and submission materials.
4. **Real Pipeline Calibration:**
   - Initial synthetic calibration completed with 100% agreement (20/20).
   - Once full 100% corpus ingestion is completed and baseline pipeline outputs exist, a formal secondary calibration pass will be conducted against 20 real pipeline outputs graded manually.

## Reconciled Document Map
- `configs/models.yaml`: `judge.model = "gemini-3.1-flash-lite-preview"`
- `reports/model_pilot_report.md`: Clarified that pro model judge requires paid billing tier.
- `src/eval/judge.py`: Fully functional two-stage evaluation with deterministic Stage 1.
