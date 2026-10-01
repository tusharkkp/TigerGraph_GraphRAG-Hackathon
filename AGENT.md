# AGENT.md — Project Guardrails

> Place at repo root. If your Antigravity build doesn't auto-load `AGENT.md`, copy it to `AGENTS.md` and/or `GEMINI.md` (both are common auto-loaded names) or to `.agent/rules/project.md`.

## 1. Project in one paragraph
Agentic GraphRAG benchmark on **TigerGraph Savanna** with **Gemini** as the LLM. We build three pipelines (RAG, GraphRAG, Agentic GraphRAG) that answer the same questions, a benchmark that compares accuracy / completeness / tokens / latency, an agent harness with an LLM orchestrator and specialised agents, and (stretch) temporal-conflict reasoning. The product *is* the evidence of **when agents help and when they don't**.

## 2. Read order at the start of every session
1. `AGENT.md` (this file) → 2. `docs/PROGRESS.md` → 3. `docs/BLOCKERS.md` → 4. `docs/DECISIONS.md` (skim titles) → 5. `git status` + `git log -10` → 6. relevant skill in `SKILLS.md`.
Then state in 3 lines: where we are, what you'll do next, how you'll verify it.

## 3. HARD RULES (never violate)

### Secrets & safety
- Never print, log, commit or paste secrets (`GEMINI_API_KEY`, TigerGraph host/user/password/secret/token). They live in `.env` only. Keep `.env` in `.gitignore`; maintain `.env.example` with placeholders.
- Before any commit run the secrets scan (`make secrets-scan`). If a secret is ever committed: stop, tell the owner, rotate the key.

### Integrity of the benchmark
- **Hidden-50 questions are never used for tuning, prompt design, threshold choice or few-shot examples.** After the first hidden run, only bug fixes are allowed; log any re-run in `docs/EXPERIMENTS.md`.
- No hard-coded answers, question IDs, or ground-truth strings anywhere in `src/`. The judge may see ground truth; pipelines never may.
- All three pipelines: same answer model, same answer-style prompt, temperature 0 for evaluation, same corpus, same output schema (`PipelineResult`). Differences must come from retrieval/reasoning only.
- Never fabricate, estimate-by-hand, or "fill in" metrics. If a run fails, store the error and report the gap.
- Do not modify tests, thresholds, judge prompts or splits to make results look better. Changing any of them requires an ADR explaining why *before* re-running.

### Token & LLM discipline
- Only `src/llm/gateway.py` talks to Gemini. No direct SDK calls elsewhere.
- Gateway responsibilities: token accounting from `usage_metadata` (input, output incl. thinking), retry w/ exponential backoff + jitter on 429/5xx, concurrency/rate limiting, disk cache keyed by (model, params, prompt hash), structured-output validation, per-call logging (agent, step, tokens, latency).
- Invariant: `total_tokens == llm_input_tokens + llm_output_tokens`; per-step tokens in a trace must sum to the question total.
- Model names come from `configs/models.yaml`, never literals in code. Validate availability at startup.
- Iterate on small subsets (`--limit`, dev split). Full 100/150-question runs only at phase gates. Print an estimated call count before big runs.

### Destructive operations (require explicit owner approval each time)
`DROP GRAPH/VERTEX/EDGE/QUERY`, deleting loaded data, wiping the LLM cache, `git push --force`, `git reset --hard` on shared branches, `rm -rf` outside `tmp/`, global `pip install`, modifying anything in `third_party/`, changing Savanna instance settings or credentials.

### Honesty
- Never claim something works without showing evidence (command output, test result, screenshot). No "should work".
- If agentic does not beat a simpler pipeline somewhere, report it plainly.
- If you are unsure about a TigerGraph/Gemini API detail, **look it up (docs/MCP/web) or write a probe script** — do not guess syntax and move on.

## 4. Stack
Python 3.11+ · pydantic v2 · pyTigerGraph (runtime) · GSQL (`graph/`) · TigerGraph vector attributes · Google GenAI SDK (Gemini) · Streamlit + Plotly · pytest · ruff · (mypy on `src/contracts.py`, `src/llm`, `src/agentic`).
TigerGraph MCP is a **dev-time helper only**; runtime code must not depend on it.

## 5. Make targets (keep these working; extend, don't rename)
```
make setup              # venv + locked deps + pre-commit
make lint               # ruff check + format --check
make test               # unit + contract (no network)
make test-integration   # live Savanna + live Gemini smoke (small)
make verify             # lint + test + fast behaviour tests   <- run before every commit
make verify-all         # verify + integration + 20-question regression bench
make ingest             # idempotent corpus -> graph load
make bench ARGS="--pipelines rag graphrag agentic --split dev --limit 10"
make app                # streamlit dashboard + demo
make validate-submission
make secrets-scan
```

## 6. Code standards
- Type hints everywhere; pydantic models at every boundary (tool I/O, LLM JSON, results).
- Small pure functions; side effects (network, disk) isolated in `llm/`, `graph/`, `eval/runner`.
- Every agent/tool: typed input/output, docstring with purpose + failure modes, unit test with recorded fixtures (no network), token/latency recorded.
- Config in YAML + env; no magic numbers in logic (k, τ, max_steps, budgets live in `configs/`).
- Structured JSON logging; every LLM call and tool call logs `question_id, pipeline, step, agent, tokens, latency_ms`.
- GSQL: one query per file in `graph/queries/`, parametrised, commented with intent, expected params and a sample call; installed via `src/graph/install.py` (idempotent).
- Ingestion is **idempotent and resumable** (stable chunk/entity IDs derived from content hashes).
- Errors: fail loudly in dev, degrade gracefully in runs (record `error`, continue with next question).
- No dead code, no commented-out blocks, no TODO without an issue line in `docs/PROGRESS.md`.

## 7. Definition of Done (per task)
- [ ] Code + tests written; `make verify` green (paste the summary)
- [ ] Relevant checks from `Automated_Verification_Loops.md` run (state which levels)
- [ ] Docs touched: `PROGRESS.md` always; `DECISIONS.md` if a choice was made; `ARCHITECTURE.md` if structure changed
- [ ] Evidence attached (test output / sample result JSON / screenshot)
- [ ] Committed on the phase branch with a conventional commit message

## 8. Working agreements with the owner
- **Plan → approve → build** for anything touching schema, contracts, agent policy, or >5 files. Small fixes: just do them and report.
- Keep messages short: what changed, evidence, what's next, anything needing a decision.
- The owner must be able to explain every design choice to judges: record the *why* and the *trade-off* in `docs/DECISIONS.md` (ADR format: Context / Options / Decision / Trade-offs / Revisit-if).
- Prefer simple and reliable over clever. Cut scope before cutting verification.
- When there are two reasonable options and the choice isn't architectural, pick one, log it, move on. Ask only if blocked.

## 9. Loop protocol (details in `LOOP_INSTRUCTIONS.md`)
Plan → Implement → Verify → Diagnose → Fix. **Max 5 iterations per task.** Same error 3 times → stop, change approach, or write `docs/BLOCKERS.md` and ask. Never loop silently on a failing check; never delete or weaken a failing check to get green.

## 10. Git
- Branch per phase: `phase/0-scaffold`, `phase/1-ingestion`, …; merge to `main` only at a green gate.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `bench:`.
- Never commit `data/raw/`, `.env`, `results/` raw dumps > 50 MB, or the LLM cache dir. Commit summaries (`reports/*.csv|md`) and the final submission files.

## 11. Terminal policy
- **Allowed freely:** read/list files, run tests/linters, run small benchmarks (`--limit ≤ 10`), start/stop the local Streamlit app, `git status/diff/log/add/commit`.
- **Ask first:** installing new dependencies (justify in one line), full-benchmark runs, schema changes on Savanna, anything that spends significant quota.
- **Forbidden:** printing `.env`, disabling SSL verification, `sudo`, piping remote scripts to a shell, anything in section 3 "Destructive operations" without approval.

## 12. Known unknowns to verify early (don't assume)
1. Savanna version & whether native vector search is available/enabled; max vector dims; index type.
2. Exact pyTigerGraph auth for Savanna (token vs. user/pass; ports 443).
3. Which Gemini models/embedding model + dimension are available to our key and their rate limits.
4. Dataset question schema (id field, category/complexity labels, answer format, multi-answer items).
5. Hidden-50 submission format (assume JSONL with `question_id, answer, tokens, trace, citations` until clarified).
6. How much of `tigergraph/graphrag` we reuse (ADR-001).

## 13. Evaluation constants (defaults; change only via ADR)
- Splits: dev 60 / val 20 / test 20 of the 100 visible questions, seed 42, stored in `data/splits.json`.
- Judge: PASS/FAIL + completeness 0–1 + grounding check; blind to pipeline; temperature 0.
- Report per pipeline and per category: accuracy, completeness, tokens (mean/median/p95), latency, cost-per-correct, with paired-bootstrap 95% CIs for pipeline differences.
