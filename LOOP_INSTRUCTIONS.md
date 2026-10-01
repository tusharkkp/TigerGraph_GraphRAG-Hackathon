# LOOP_INSTRUCTIONS.md

Five nested loops. Antigravity must follow them literally. Loops 1–2 govern *how you build*; Loop 3 governs *how you improve benchmark results*; Loop 4 is the *runtime loop inside the product*; Loop 0 is the session ritual.

```
Loop 0  Session         (start/end ritual)
 └─ Loop 2  Phase       (gate-driven)
     └─ Loop 1  Task    (plan → implement → verify → diagnose → fix)
 └─ Loop 3  Improvement (benchmark → error analysis → one change → re-run)
Loop 4  Runtime agent loop (inside the product, specified for the harness)
```

---

## Loop 0 — Session ritual

**Start**
1. Read `AGENT.md`, `docs/PROGRESS.md`, `docs/BLOCKERS.md`, titles in `docs/DECISIONS.md`, `git status`, `git log -10`.
2. Output exactly: `STATE:` (2 lines) · `TODAY'S GOAL:` · `VERIFICATION PLAN:` (which levels / commands).
3. Ask nothing unless blocked.

**End**
1. Run `make verify`. Fix or record failures.
2. Update `docs/PROGRESS.md` (done / in-progress / next / numbers) and `docs/EXPERIMENTS.md` if any run happened.
3. Commit (green only; else commit to a `wip/` branch and say so). Print a 5-line handoff summary.

---

## Loop 1 — Task loop (inner)

```
PLAN → IMPLEMENT → VERIFY → (pass? → REFLECT → DONE) / (fail? → DIAGNOSE → FIX → VERIFY …)
```
1. **PLAN** — restate the task and acceptance criteria; list files to touch, tests to add, the verification levels (see `Automated_Verification_Loops.md`), and top 2 risks. For schema/contract/agent-policy changes or >5 files: **stop for approval**.
2. **IMPLEMENT** — smallest change that could satisfy the criteria; tests first or alongside.
3. **VERIFY** — run `make verify` (+ any L4/L5 needed). Capture output.
4. **DIAGNOSE** (on failure) — follow `debugging-protocol`: reproduce → read the actual error → ≤3 hypotheses → cheapest discriminating experiment.
5. **FIX** — fix the cause; add a regression test.
6. **REFLECT** (on success) — anything fragile? any ADR to write? update docs. Output the evidence block from `Automated_Verification_Loops.md §12`.

**Limits & escalation**
- Max **5** VERIFY cycles per task.
- Same failure signature **3×** → stop, change approach (different hypothesis class), or write `docs/BLOCKERS.md` (what you tried, evidence, options) and ask.
- Never: delete/skip/xfail tests, loosen thresholds, mock away a failing live dependency in benchmark paths, or retry blindly.
- If the task grows beyond the plan, stop and re-plan (don't silently expand scope).

---

## Loop 2 — Phase loop (middle)

For each phase in the Master Prompt:
1. Write the **Phase Plan** (tasks, order, gate checklist, risks) → owner approves.
2. Execute tasks with Loop 1; after each, tick the gate checklist in `PROGRESS.md`.
3. **Gate review:** run `make verify-all`; present the gate evidence; list deviations and ADRs.
4. Owner says "gate approved" → merge branch → next phase. If a gate can't be met within the time-box, propose a scoped-down gate (don't quietly move on).

**Time-boxes (guideline for a 7-day sprint):** P0 ≤ 3 h · P1 ≤ 6 h · P2 ≤ 6 h · P3 ≤ 10 h · P4 ≤ 8 h · P5 ≤ 3 h · P6 ≤ 10 h · P7 ≤ 8 h · P8 ≤ 4 h. When 150% of a time-box is spent, trigger a scope review.

---

## Loop 3 — Improvement loop (benchmark-driven)

Purpose: raise accuracy per token **without overfitting**.

```
BASELINE → ERROR ANALYSIS → HYPOTHESIS → ONE CHANGE → RE-RUN (dev) → CHECK (val) → ACCEPT / REVERT → LOG
```
1. **Baseline:** frozen results for the three pipelines on `dev` (and `val`). Commit as `reports/baseline.json`.
2. **Error analysis:** for every FAIL (agentic first, then GraphRAG, then RAG), read the trace and retrieved chunks; assign exactly one root-cause label:
   `entity_link_miss` · `retrieval_miss` · `wrong_hop/relationship` · `aggregation_error` · `reasoning_error` · `stopped_too_early` · `over_retrieved_noise` · `ground_truth_ambiguous` · `judge_error` · `answer_format` · `tool_error` · `temporal_conflict_error`.
   Output a count table + 3 representative examples per label.
3. **Hypothesis:** pick the label with the largest (count × fixability); write the hypothesis and expected effect in `EXPERIMENTS.md` *before* changing code.
4. **ONE change** only (prompt, k, hop depth, tool, evaluator threshold, stop rule, chunking). Never bundle changes.
5. **Re-run on dev** (`--limit` for speed first, then full dev). Compare vs baseline: accuracy, completeness, tokens, latency.
6. **Check on val** (never tune on val directly). Accept only if: dev improves meaningfully **and** val doesn't regress beyond noise **and** token overhead is justified.
7. **Accept/Revert + log** (what, why, numbers, decision). Update baseline on accept.
8. Stop the loop when: (a) top failure label is `ground_truth_ambiguous`/`judge_error`, (b) 3 consecutive experiments give no gain, or (c) time-box ends.

**Anti-overfitting rules**
- Never add question-specific rules, strings, or few-shot examples copied from dev/val/test/hidden questions' answers.
- Few-shot examples for prompts are **synthetic or from the corpus**, not from evaluation questions.
- Hidden-50 outputs are not inspected for tuning. After the first hidden run: bug fixes only, logged.
- Final report states which numbers are dev (tuned), val (checked) and test (untouched).

**Efficiency sub-loop (agent token diet):** after accuracy plateaus, look for token waste: repeated evidence in prompts, evaluator called too often, verbose tool outputs, orchestrator state too large. Reduce one at a time, re-run val, accept if accuracy holds and tokens drop ≥10%.

---

## Loop 4 — Runtime agent loop (spec for the product's harness)

```
INIT    state ← {question, budgets, empty ledger}
LOOP    until STOP:
  OBSERVE   compact_view(state)                       # question, subquestions, entities, top evidence, gaps, budgets
  DECIDE    orchestrator → {rationale, action, args, strategy_tag}
  GUARD     validate schema; reject repeated (tool,args); enforce budgets; fallback if invalid
  ACT       run tool/agent → observation (+tokens, latency)
  UPDATE    ledger += evidence; trace += step; detect strategy change
  EVALUATE  (every k steps or when orchestrator asks) → sufficient? gaps? contradictions?
  STOP?     sufficient∧conf≥τ | max_steps | max_tokens | max_time | no_new_evidence×N | loop_detected | GIVE_UP
ANSWER  grounded answer with citations + explicit uncertainty if budget-stopped or conflicting
EMIT    PipelineResult (answer, citations, tokens, latency, trace, stop_reason, strategy_changed)
```
Invariants: every iteration appends exactly one `TraceStep`; every stop sets `stop_reason`; per-step tokens sum to the total; no tool call without being logged; orchestrator never sees more than the compact view + requested evidence snippets.

---

## Reusable slash-workflows (put in `.agent/workflows/` or paste as prompts)

**/start-session** — "Follow Loop 0 start. Then wait for my goal."

**/plan-task** — "Create an Implementation Plan for: <task>. Include acceptance criteria, files, tests, verification levels, risks, and whether it needs my approval. Do not code yet."

**/verify** — "Run `make verify`. Report the evidence block. If anything fails, enter Loop 1 DIAGNOSE; stop after 5 cycles or 3 identical failures."

**/diagnose** — "Apply debugging-protocol to: <failure>. Reproduce, list ≤3 hypotheses with discriminating experiments, run the cheapest, report. Do not change code until the cause is evidenced."

**/gate** — "Run `make verify-all`, assemble the gate checklist for phase <n> with evidence for each item, list ADRs and deviations, and recommend approve/not-approve."

**/improve** — "Run Loop 3 once for pipeline <p> on dev. Output the error-label table, your hypothesis, the single change proposed, and wait for my OK before editing."

**/bench-small** — "Run `make bench ARGS='--pipelines rag graphrag agentic --split val --limit 10'` and summarise accuracy, tokens, failures, and any invariant violations."

**/explain-design** — "Explain <component> as if I must defend it to judges: the design, 3 alternatives considered, the trade-offs, how it was verified, its weaknesses. Add it to `docs/DECISIONS.md`."

**/end-session** — "Follow Loop 0 end."

---

## Termination & escalation summary

| Situation | Action |
|---|---|
| Task passes all required checks | Output evidence, mark done, next task |
| 5 verify cycles used | Stop, write BLOCKERS entry with options, ask owner |
| Same failure 3× | Change hypothesis class or ask; no more blind retries |
| Needs destructive action / secret / paid quota | Ask owner explicitly |
| Requirement ambiguity affecting architecture | Ask one concise question with a recommended default |
| Free-tier quota exhausted | Pause LLM-heavy work; switch to offline tasks (tests, docs, dashboard with existing results) |
| Behind schedule at 150% of a time-box | Propose scope cut (order: router → extra dataset → temporal breadth); never cut verification or the benchmark |

## Context hygiene
- New conversation per phase; always resume via Loop 0.
- Keep `PROGRESS.md` ≤ 150 lines (archive older entries to `docs/archive/`).
- Don't paste large result dumps into chat; write them to files and reference paths.
- Prefer referring to `contracts.py` over re-describing schemas.
