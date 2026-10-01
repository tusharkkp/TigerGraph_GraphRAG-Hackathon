# SKILLS.md — Project Skills for Antigravity

How to use: keep this file at repo root so the agent can read the skill it needs, **or** split each `## SKILL:` block into `.agent/skills/<skill-name>/SKILL.md` (the YAML frontmatter at the top of each block is already in that format). Before starting a task, the agent states which skill(s) it is applying.

Rule for all skills: **if an API detail is uncertain, probe it (small script / docs / MCP) and record what you learned in the skill's "Verified notes" section in `docs/DECISIONS.md`.** Code snippets below are skeletons, not verified syntax.

---

## SKILL: tigergraph-savanna-ops
```yaml
---
name: tigergraph-savanna-ops
description: Connect to TigerGraph Savanna, manage schema/loading/queries safely with pyTigerGraph and GSQL. Use for any graph DB interaction.
---
```
**When:** connecting, creating schema, loading data, installing/running queries, vector attributes, debugging Savanna errors.

**Procedure**
1. Read creds from `.env` (`TG_HOST`, `TG_GRAPH`, `TG_USERNAME`, `TG_PASSWORD` or `TG_SECRET`/`TG_TOKEN`). Never print them.
2. Connection via `TigerGraphConnection(host=..., graphname=..., ...)`; Savanna is HTTPS (port 443 for REST/GSQL) — confirm by probe, don't assume. Wrap in `src/graph/client.py` with retries and timeouts; expose `run_query(name, params)`, `upsert_vertices`, `upsert_edges`, `vector_search`, `schema_summary()`.
3. Schema lives in `graph/schema.gsql`; changes go through `graph/migrations/` (idempotent, ordered). Never edit the live schema by hand without recording the migration.
4. **Vector attributes:** verify the instance version supports them; choose dimension = embedding model's output dimension (config); test round-trip (insert → search → expected top-1) before loading the corpus.
5. Loading: batch upserts (e.g. 500–1000 per request), stable IDs (hash of content), resumable with a checkpoint file; verify counts afterwards by querying vertex/edge counts.
6. Queries: install from `graph/queries/*.gsql` through `src/graph/install.py` (skip if unchanged). Every query has a smoke test with a known seed entity.
7. Safety: no `DROP` without approval; before destructive ops, export counts and ask.

**Gotchas to probe**
- Cold/suspended instances → first calls time out; add a `wait_until_ready()` helper.
- Large result sets → always `LIMIT` and project only needed attributes.
- Accumulator-heavy queries can be slow; test on small k first.
- Auth tokens expire → refresh on 401 once, then fail loudly.

**Done when:** connection smoke test, schema summary printout, vector round-trip test, query smoke tests all green.

---

## SKILL: gsql-query-authoring
```yaml
---
name: gsql-query-authoring
description: Write parametrised, tested GSQL queries for traversal, aggregation and fact/temporal lookups used by the agents.
---
```
**Query catalogue to implement (one file each, in `graph/queries/`)**
- `entity_lookup(name, alias_list)` – exact/alias match, returns candidates + scores.
- `neighbors_k_hop(entity_id, hops, edge_types, limit)` – typed expansion with relationship evidence chunk IDs.
- `shortest_path(entity_a, entity_b, max_hops)` – returns path vertices/edges + evidence.
- `chunks_for_entities(entity_ids, limit, include_neighbors)` – supporting chunks ranked by mention count/relationship weight.
- `entity_rel_summary(entity_id)` – degree by edge type (helps orchestrator choose strategy).
- `aggregate_by_type(entity_ids|filter, group_by, agg)` – counts/min/max/avg done in-DB.
- `community_summaries(entity_ids)` – for global/summary questions (if communities built).
- (stretch) `facts_for(subject, predicate)`, `fact_history(subject, predicate)`, `conflicts_for(subject)`.

**Skeleton (verify syntax against the installed version before use)**
```gsql
CREATE QUERY neighbors_k_hop(VERTEX<Entity> seed, INT hops = 2, INT lim = 50) FOR GRAPH <GRAPH> SYNTAX v2 {
  OrAccum<BOOL> @@visited;
  SetAccum<VERTEX<Entity>> @@frontier;
  // ... iterative expansion over RELATES_TO with hop counter, collect evidence chunk ids
  PRINT @@frontier;
}
```
**Rules:** parameterised (no string concatenation of user text), commented header (intent, params, sample call), bounded (`LIMIT`, hop cap), returns IDs + minimal attributes, has a unit/integration test with expected row count on a seed entity.

---

## SKILL: gemini-llm-gateway
```yaml
---
name: gemini-llm-gateway
description: Build and use the single LLM gateway for Gemini with exact token accounting, retries, rate limiting, caching and structured output.
---
```
**Interface**
```python
class LLMGateway:
    def generate(self, *, role: str, prompt: str|list, schema: type[BaseModel]|None=None,
                 temperature: float=0.0, tag: CallTag) -> LLMResult   # text/parsed, usage, latency, cache_hit
    def embed(self, texts: list[str], *, task: str) -> EmbedResult
```
**Requirements**
- Tokens from the response's usage metadata: prompt tokens, candidate/output tokens, and thinking tokens (if the model reports them) added to output. Cached responses replay **recorded** usage but flag `cache_hit=True`; reports show both "billed" and "logical" tokens (logical is what the benchmark compares).
- Retry on 429/5xx with exponential backoff + jitter; respect `retry-after`; global concurrency semaphore + requests-per-minute token bucket from `configs/models.yaml`.
- Disk cache: key = sha256(model, params, system, prompt, schema); store response + usage; `--no-cache` flag for determinism checks.
- Structured output: ask for JSON (use the SDK's JSON/schema mode if available), validate with pydantic, **one** repair attempt, then raise `LLMSchemaError`.
- Roles: `orchestrator`, `agent`, `answer`, `judge`, `extract`. Each maps to a model/params in config (answer model identical across pipelines; judge ideally a different model from answerer).
- Startup check: list models, assert configured ones exist and embedding dim matches the graph's vector dim.
- Logging: JSON line per call (tag: question_id, pipeline, step, agent) → `logs/llm_calls.jsonl`.

**Tests:** simulated 429 retry; cache hit; schema-repair path; usage summation; invariants.

---

## SKILL: graphrag-ingestion
```yaml
---
name: graphrag-ingestion
description: Turn the provided corpus into a TigerGraph knowledge graph with chunks, entities, relations and embeddings, idempotently.
---
```
**Pipeline:** load docs → clean → chunk (start 400–600 tokens, 10–15% overlap; tune via ADR) → extract entities+relations per chunk with the `extract` role (structured JSON, include evidence chunk ID and a short quote) → normalise/merge aliases (embedding + string similarity, conservative thresholds) → embed chunks (and entity descriptions) → upsert → compute stats.

**Quality controls**
- Extraction prompt includes the **entity type list and relation type list** (derive from corpus sample + ADR) to avoid schema explosion.
- Dedup: canonical entity ID = hash(type + normalised name); keep `aliases[]`.
- Report: #docs, #chunks, #entities, #relations, avg degree, orphan entities %, top-20 entities by degree, 10 random relation samples with source quotes for **manual spot check** (owner reviews).
- Cost control: cache extraction per chunk hash; support `--limit docs`; estimate calls before running.
- Optional: community detection (Leiden/Louvain via TigerGraph algorithms) + LLM summaries for global-question support — only if the dataset has global/summary questions.
- Optionally compare against `tigergraph/graphrag` ingestion on a sample (ADR-001).

**Done when:** idempotent re-run adds 0 duplicates; stats report committed; spot-check sample reviewed.

---

## SKILL: agent-harness-design
```yaml
---
name: agent-harness-design
description: Design and implement the orchestrator, specialised agents, evidence ledger, budgets and stopping logic for Agentic GraphRAG.
---
```
**Core loop (in `harness.py`)**
```python
state = AgentState(question, budgets)
while not stopper.should_stop(state):
    view  = state.compact_view()                       # NOT the full transcript
    act   = orchestrator.next_action(view, tools.catalogue())   # JSON: rationale, action, args, strategy_tag
    act   = guard(act, state)                          # validate args, block repeats, enforce budgets
    obs   = tools.run(act)                             # typed result + tokens + latency
    state.record(act, obs)                             # ledger update, trace step, strategy detection
    if act.action in {"EVALUATE", "ANSWER"} or state.step % eval_every == 0:
        state.apply(evidence_evaluator(state))         # sufficiency, gaps, contradictions
return answer_agent.write(state)                       # grounded, cited, uncertainty-aware
```
**Orchestrator system prompt must contain:** role; tool catalogue with *when to use / cost hint*; the cheap-first principle; budget remaining; rules (don't repeat identical calls, target the stated gaps, say ANSWER as soon as evidence suffices, GIVE_UP with uncertainty rather than loop); 3 diverse example paths; strict JSON schema; "rationale = one or two sentences, no hidden chain-of-thought".

**Evidence ledger item:** `{id, kind: chunk|entity|path|fact|aggregate, text, source_ref, step, relevance, supports: [subq_ids], contradicts: [ids]}`. Compact view shows the top-N items by relevance with 1-line summaries; full text only when needed for the final answer.

**Evaluator contract:** `{sufficient: bool, confidence: 0-1, per_subquestion: [...], missing: [str], contradictions: [(id,id,why)]}`; temperature 0; short outputs.

**Stopping:** sufficient∧conf≥τ · max_steps · max_tokens · max_time · no-new-evidence N · loop-detected · GIVE_UP. Always set `stop_reason`.

**Strategy change:** compare primary modality of consecutive productive attempts; if switch follows an `insufficient` evaluation → `decision="change_strategy"` with reason.

**Design trade-offs to document (ADR):** planner-per-step vs. plan-then-execute; evaluator frequency vs. token cost; compact state size; deterministic tools vs. LLM tools; τ and N values.

**Anti-patterns:** fixed tool order, passing the whole history each turn, LLM doing arithmetic, unbounded retries, silent catch of tool errors.

---

## SKILL: benchmark-eval
```yaml
---
name: benchmark-eval
description: Run the 3-way benchmark, judge answers, compute metrics with confidence intervals, and analyse where agents add value.
---
```
**Runner:** `python -m src.eval.runner --pipelines rag graphrag agentic --split dev --limit N --run-id X`; resumable; concurrent with caps; one JSON per (pipeline, question).

**Judge prompt template (blind to pipeline)**
```
You are grading an answer against a ground-truth reference.
Question: {question}
Ground truth: {ground_truth}
Candidate answer: {answer}
Rules: PASS only if the candidate gives the same essential facts as the ground truth and contains no
contradicting claim. Extra correct detail is fine. Missing a required fact => FAIL.
Return JSON: {"verdict":"PASS|FAIL","completeness":0..1,"missing_facts":[...],"contradictions":[...],"reason":"<=40 words"}
```
**Grounding check:** programmatic — every cited `quote` is a substring of its chunk; plus sampled LLM check "is each claim supported by the cited evidence?".

**Metrics:** accuracy, completeness, grounding, tokens (context/input/output/total; mean, median, p95), latency, cost-per-correct, error rate. Agentic extras: steps, tools used, strategy-change rate, stop-reason distribution, tokens per step, tokens by agent.

**Analysis:** per-category table; paired bootstrap (10k resamples) for agentic−graphrag and graphrag−rag accuracy; win/loss/tie matrix; Pareto (accuracy vs mean tokens); "overkill" list (questions where RAG passed and agentic cost ≥ k× more); "only-agent-wins" list; failure taxonomy counts. Write `reports/findings.md` stating conclusions *with numbers*.

**Optional router:** features = question length, #entities linked, question-type classifier, cheap RAG-retrieval confidence → predict cheapest sufficient pipeline; evaluate vs always-X and oracle on val/test.

**Done when:** reports regenerate from raw results with one command and match the dashboard.

---

## SKILL: temporal-conflict-reasoning
```yaml
---
name: temporal-conflict-reasoning
description: Detect conflicting versions of facts, decide supersession, rank source authority and express calibrated uncertainty (Round 2 stretch).
---
```
**Data model:** `Fact{subject,predicate,value,valid_from,valid_to,asserted_at,confidence}` ← `ASSERTS` ← `Chunk`; `Source{type,authority_score}`; edges `SUPERSEDES`, `CONFLICTS_WITH`.

**Steps**
1. Extract dated claims (structured JSON; keep quote + span). Normalise dates, units, entity IDs.
2. Group by (subject, predicate); detect value disagreement within overlapping validity.
3. Resolve with an explicit, documented policy, e.g. score = w1·recency(asserted_at / valid_from) + w2·authority + w3·corroboration + w4·explicit-revision-language ("postponed", "revised", "replaced", "withdrawn"); weights in `configs/temporal.yaml`; tune on a dev conflict set, not the hidden one.
4. Authority: classify source types (official announcement > regulatory filing > major news > blog/forum), configurable and justified in an ADR.
5. Uncertainty: confidence reflects score margin between top two candidates and corroboration; if margin < δ → answer states both versions and says it cannot determine which is current.
6. Answer format: current best value · what it superseded and when · conflicting sources · confidence.

**Evaluation:** build ≥30 conflict cases (date shifts, retractions, low-authority contradictions, multi-hop temporal); metrics: resolution accuracy, correct-supersession rate, calibration (confidence vs correctness), % of unresolvable cases correctly flagged.

---

## SKILL: trace-and-dashboard
```yaml
---
name: trace-and-dashboard
description: Build the Streamlit dashboard, side-by-side demo and investigation-trace visualisation.
---
```
- Read only from `results/` and `reports/` (dashboard never calls pipelines except the live demo page).
- Pages: **Overview** (table + key finding), **By category**, **Efficiency** (Pareto, cost-per-correct), **Agent lift** (CIs), **Question drill-down** (three answers, citations, tokens), **Trace viewer**, **Live demo**, **Temporal cases** (stretch).
- Trace viewer: timeline of steps (agent, tool, args summary, evidence added, tokens, ms), colour by strategy_tag, highlight `change_strategy` and `stop`; right panel shows evidence ledger and the subgraph (entities/edges used) via networkx/pyvis or Plotly.
- Accessibility/readability: units labelled, no unlabeled axes, consistent colours per pipeline.
- Verify with the browser agent (L7) and keep screenshots for the demo video.

---

## SKILL: submission-packaging
```yaml
---
name: submission-packaging
description: Produce validated hidden-50 outputs, architecture diagram, README, writeup and demo assets.
---
```
1. `scripts/export_hidden.py` runs the pipelines on the 50 hidden questions with `temperature 0`, writes `submission/hidden50_<pipeline>.jsonl` (`question_id, answer, tokens{context,input,output,total}, citations, trace, stop_reason, latency_ms`).
2. `scripts/validate_submission.py` (L6) must pass; keep `submission/MANIFEST.md` (git commit hash, model names, config hashes, date, run IDs).
3. Architecture diagram: Mermaid source in `docs/ARCHITECTURE.md` + exported PNG/SVG; shows data flow, three pipelines, harness/agents, evaluator, dashboard.
4. README: what/why, quickstart (clean-clone verified), config, how to reproduce results, repo map, limitations.
5. Writeup (≤2 pages): what we built, how it works, key results with numbers, limitations, what we'd do with more time.
6. Demo video script from `docs/demo_script.md`; record using screenshots/walkthrough artifacts.
7. Final checks: secrets scan, license, clean-clone check, links in README work.

---

## SKILL: debugging-protocol
```yaml
---
name: debugging-protocol
description: Systematic root-cause debugging for failing tests, bad answers and infra errors; prevents blind retry loops.
---
```
1. **Reproduce** minimally (one question / one test) and save the exact command.
2. **Observe:** read the full error/trace/log lines; for bad answers read the pipeline trace and the retrieved chunks, not just the answer.
3. **Hypothesise** (max 3, ranked) → **cheapest discriminating experiment** for each.
4. **Fix the cause**, not the symptom; add a regression test that fails before and passes after.
5. **Re-verify** at the level where it failed plus L0–L3.
6. **Log** in `EXPERIMENTS.md` (symptom → cause → fix). If the same error persists after 3 attempts, stop and escalate per `LOOP_INSTRUCTIONS.md`.
