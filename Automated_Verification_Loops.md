# Automated Verification Loops

Goal: every change is proven by **machine-checkable evidence** before it counts as done. Antigravity must run the relevant level(s), paste the results, and only then mark a task complete.

## 0. Levels at a glance

| Level | Name | Network? | When it runs | Command |
|---|---|---|---|---|
| L0 | Static | no | every save / pre-commit | `make lint` |
| L1 | Unit | no | every task | `make test` |
| L2 | Contract | no | every task touching pipelines/agents | `make test` (marker `contract`) |
| L3 | Behaviour (agentic) | no (recorded LLM fixtures) | every agentic change | `pytest -m behavior` |
| L4 | Integration | yes (small) | phase gates, infra changes | `make test-integration` |
| L5 | Regression benchmark | yes | before merge to main, after tuning | `make verify-all` |
| L6 | Submission validators | no | before any export | `make validate-submission` |
| L7 | UI / E2E (browser agent) | local app | UI changes, final gate | `make e2e` + screenshots |
| L8 | Clean-clone reproducibility | yes | Phase 8 | `scripts/clean_clone_check.sh` |

`make verify` = L0 + L1 + L2 + L3. **Run it before every commit.**

## 1. L0 — Static
- `ruff check .`, `ruff format --check .`, mypy on `src/contracts.py src/llm src/agentic`.
- `make secrets-scan` (regex + `gitleaks`/`detect-secrets` if installable): fails on anything resembling an API key, TigerGraph secret, token, or `.env` content.
- Forbidden-pattern grep (fail if found in `src/`): direct `genai.`/`google.generativeai` imports outside `src/llm/`; literal model names (`gemini-`) outside `configs/`; ground-truth field access in `src/pipelines|agentic`; `print(` of env vars.

## 2. L1 — Unit tests (no network)
Must cover at minimum:
- `llm/cache`: same prompt → cache hit, no second API call; different params → miss.
- `llm/gateway`: retry/backoff on simulated 429; token accounting sums; structured-output repair/reject path.
- `ingestion`: chunk IDs stable across runs; re-ingest creates 0 duplicates (idempotency).
- `graph/client`: GSQL param building; error mapping.
- `eval/metrics`: accuracy, completeness, cost-per-correct, percentile functions against hand-computed examples.
- `eval/stats`: paired bootstrap on known toy data returns expected CI direction.
- `eval/splits`: deterministic with seed; no overlap between dev/val/test; hidden IDs never appear in splits.
- Each agent/tool: typed I/O, handles empty results, handles tool error.

## 3. L2 — Pipeline contract tests (parametrised over rag, graphrag, agentic)
Run each pipeline on 3 canned questions using **recorded** LLM/graph fixtures and assert:
```python
@pytest.mark.contract
@pytest.mark.parametrize("pipeline", ["rag", "graphrag", "agentic"])
def test_pipeline_contract(pipeline, fixtures):
    r = run_pipeline(pipeline, fixtures.question, replay=True)
    assert isinstance(r, PipelineResult)
    assert r.answer.strip()
    t = r.tokens
    assert t.total_tokens == t.llm_input_tokens + t.llm_output_tokens
    assert t.context_tokens <= t.llm_input_tokens
    assert all(c.chunk_id in fixtures.chunk_ids for c in r.citations)      # no invented citations
    assert all(c.quote is None or c.quote in fixtures.chunk_text[c.chunk_id] for c in r.citations)
    if pipeline == "agentic":
        assert r.trace and r.stop_reason
        assert sum(s.tokens_in + s.tokens_out for s in r.trace) == t.total_tokens
        assert all(s.decision in {"continue","change_strategy","stop"} for s in r.trace)
        assert r.trace[-1].decision == "stop"
    if pipeline == "rag":
        assert r.trace == []
```
Also: a pipeline must **never read ground truth** (test passes a question object that has no `answer` field).

## 4. L3 — Behaviour tests for the agent harness (the part judges care about)
Use a scripted fake orchestrator/LLM + fake tools so tests are deterministic.
1. **Stops when sufficient:** evaluator returns sufficient on step 2 → harness stops at step 2, `stop_reason="sufficient_evidence"`.
2. **Budget enforcement:** with `max_steps=3`, never exceeds 3 tool calls; `stop_reason="max_steps"`; still returns a best-effort answer flagged uncertain. Same for `max_tokens`, `max_wall_time`.
3. **Loop detection:** orchestrator proposes identical (tool,args) twice → harness blocks it, forces re-plan or stop; logged.
4. **No-progress stop:** N steps with zero new relevant evidence → `stop_reason="no_new_evidence"`.
5. **Strategy change logged:** vector search returns nothing useful → orchestrator switches to graph traversal → trace has a step with `decision="change_strategy"` and a reason.
6. **Gap follow-up:** evaluator reports missing info X → next action targets X (assert args reference X).
7. **Contradiction surfaced:** two ledger items contradict → evaluator flags it; final answer mentions uncertainty/conflict (stretch: supersession chosen correctly).
8. **Easy-question efficiency:** on a single-hop fixture the agent finishes in ≤2 retrieval steps (guards against agent over-thinking).
9. **Tool failure resilience:** a tool raises → recorded in trace, orchestrator picks an alternative, run does not crash.
10. **Trace replay:** serialise → deserialise → identical; trace JSON validates against schema.
11. **Orchestrator output validation:** malformed JSON → one repair attempt → else safe fallback action (answer with current evidence).

## 5. L4 — Integration (live, small, cheap)
- Savanna: connect; schema present; vector attribute round-trip (insert 3 chunks with embeddings → top-1 search returns the right one); each installed GSQL query returns expected shape on a seed entity; idempotent re-load.
- Gemini: generate returns text + usage metadata; embed returns correct dimension; configured models exist; cache hit on repeat call.
- End-to-end smoke: 3 questions × 3 pipelines produce valid `PipelineResult`s and non-empty answers.
- Mark with `@pytest.mark.integration`; skip automatically if env vars are missing (but `make verify-all` fails if they are missing).

## 6. L5 — Regression benchmark
**Smoke bench (`--split val --limit 20`)** after any retrieval, prompt, agent-policy or model-config change. Gates (initial defaults, set real values after baselines in Phase 2 and record via ADR):
- Error/crash rate < 2%.
- Agentic accuracy ≥ GraphRAG accuracy − 3 pts on val (agent must not be *worse* than the simpler baseline by more than noise).
- Mean agentic total tokens ≤ configured cap (e.g. 6× GraphRAG mean) — otherwise flag for efficiency work.
- Citation validity ≥ 95% (quotes found in cited chunks).
- No metric moves by more than ±5 pts vs. last committed `reports/baseline.json` without an `EXPERIMENTS.md` entry explaining why.
- Token invariants hold on 100% of results.

**Judge reliability loop** (once per judge-prompt change): sample 20 judged results, owner or Antigravity re-grades by reading ground truth manually, compute agreement; require ≥ 85% agreement or fix judge prompt.

**Determinism check:** rerun 5 questions with cache disabled at temperature 0; answers should be near-identical; report variance (low-level non-determinism is expected — document it).

## 7. L6 — Submission validators (`scripts/validate_submission.py`)
- File exists per required pipeline; exactly **50** unique question IDs; IDs match the hidden question file.
- Required fields present and typed: `question_id, answer, tokens{context,input,output,total}, trace[], citations[]`.
- No empty answers (error rows are allowed only if explicitly `error` + flagged in report).
- Token invariants and per-step sums hold.
- No ground-truth/judge fields leaked into the file; no secrets.
- Trace steps include: agent, tool, args, tokens, latency, strategy_tag, decision; last step is `stop` with `stop_reason`.

## 8. L7 — UI/E2E with the Antigravity browser agent
1. `make app` (background). Open the local URL.
2. Dashboard: confirm 3 pipelines appear in the summary table; numbers match `reports/summary.csv` (read both, compare); category chart renders; Pareto chart renders. Capture screenshots into `reports/e2e/`.
3. Demo page: ask a canned question; verify three answers, token counters, and the trace timeline appear; the "stop reason" is displayed; the evidence subgraph renders.
4. Error handling: submit empty input and an unanswerable question → friendly message, no stack trace.
5. Save screenshots + a short walkthrough artifact; these double as demo-video material.

## 9. L8 — Clean-clone reproducibility (Phase 8)
`scripts/clean_clone_check.sh`: clone repo to temp dir → follow README only → `make setup` → `make test` → `make ingest --dry-run` (or against a scratch graph) → `make bench ARGS="--limit 3"` → `make app` smoke. Any step needing undocumented knowledge fails the check and gets fixed in README.

## 10. Metric invariants (assert in code and tests)
1. `total_tokens = llm_input_tokens + llm_output_tokens`.
2. `context_tokens ≤ llm_input_tokens`.
3. Σ per-step tokens == question total (agentic).
4. `0 ≤ completeness ≤ 1`; PASS ⇒ completeness > 0.
5. Every citation ID exists in the graph; every quote is a substring of its chunk.
6. #questions in results == #questions requested (no silent drops).
7. Same question + same pipeline + same run_id never appears twice.

## 11. Failure triage table (what to do when a check fails)

| Symptom | Likely cause | First action |
|---|---|---|
| 429 / quota errors | rate limits | lower concurrency, raise backoff, rely on cache, shrink subset |
| Token invariant fails | an LLM call bypassed the gateway | grep for direct SDK use; route through gateway |
| Agent loops/never stops | stop rules not enforced or orchestrator prompt lacks budget | check `stopping.py` tests; add budget to prompt state |
| Agent worse than GraphRAG | over-retrieval, wrong stop, entity-link failures | inspect traces of failed items; categorise (see LOOP §3) |
| Accuracy drop after prompt tweak | prompt regression | revert; A/B on val; log in EXPERIMENTS.md |
| Citations invalid | LLM paraphrased quote | enforce quote-substring check; ask model for chunk IDs + short quote; post-validate |
| Savanna timeouts | heavy GSQL / cold instance | add LIMIT, reduce hops, check instance is running, retry |
| Judge disagrees with manual grade | judge prompt too lenient/strict | tighten rubric, add counter-examples, re-run calibration |
| Flaky test | non-determinism | fix with fixtures/seeds; never `retry` blindly |

## 12. Evidence format Antigravity must output at the end of each task
```
TASK: <name>
LEVELS RUN: L0 L1 L2 L3
RESULT: PASS (n tests, 0 failed)  | key command outputs or file paths
METRICS (if bench): accuracy, completeness, mean tokens, p95 latency, vs baseline
ARTIFACTS: files changed, screenshots, result JSON paths
RISKS / FOLLOW-UPS: ...
```

## 13. Rules about the checks themselves
- Checks may be **added or tightened** freely; **loosened or deleted only with an ADR and owner approval.**
- A failing test is information: fix the code, or explain in an ADR why the test is wrong. Never skip, xfail or comment out to reach green.
- Recorded fixtures live in `tests/fixtures/`; re-record only deliberately (`make record-fixtures`) and review the diff.
