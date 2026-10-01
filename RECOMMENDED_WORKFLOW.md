# Recommended Workflow (you + Antigravity)

> Feature names below (Planning vs Fast mode, Agent Manager, Artifacts, `.agent/` folders, workflows) reflect Antigravity as commonly documented; menu labels may differ slightly in your version.


## 1. One-time setup
1. **Repo:** `git init`, create GitHub repo (public at the end), add the five pack files + `.env.example`.

2. **Antigravity project config:**
   - Open the repo as the workspace; make sure `AGENT.md` is at the root (copy to `AGENTS.md`/`GEMINI.md` if it isn't picked up).
   - Optional structure for auto-discovery: `.agent/rules/` (project rules), `.agent/skills/<name>/SKILL.md` (split from `SKILLS.md`), `.agent/workflows/<name>.md` (the slash-workflows in `LOOP_INSTRUCTIONS.md`).
   - **Terminal policy:** use "request review"/ask-before-run for commands at first; relax to auto-approve only for the safe list in `AGENT.md §11` once you trust it.
   - **Optional MCP:** add TigerGraph MCP (follow its README) so the agent can inspect the schema and test GSQL interactively.
3. **Model/mode:** use **Planning mode** with your strongest available model for architecture, multi-file work and agent design; **Fast mode** for small edits, test fixes, doc tweaks.

## 2. Daily rhythm
**Start of day (10 min)**
- New conversation (or continue) → paste: *"Follow AGENT.md session start. Summarise state, today's goal, verification plan."*
- Review `docs/PROGRESS.md`; set 1–3 concrete goals.

**During the day — loop per task (see LOOP_INSTRUCTIONS.md)**
1. Ask for an **Implementation Plan artifact** → read it critically (30–60 s) → approve or comment inline.
2. Let the agent implement → it runs `make verify` → reads evidence.
3. Review the **diff + walkthrough artifact**; spot-check one risky file yourself.
4. Commit when green.

**End of day (10 min)**
- Run `/end-session` workflow: update `PROGRESS.md`, `EXPERIMENTS.md`, commit, push.
- Skim token spend; plan tomorrow's full-benchmark runs sparingly (free-tier quotas).

## 3. Parallel agents in Agent Manager (only after Phase 0)
Run at most 3 at once, each with a distinct file-ownership boundary:
| Agent | Owns | Task examples |
|---|---|---|
| A — Data/Graph | `src/ingestion`, `graph/` | schema, extraction, loading, GSQL queries |
| B — Pipelines/Agentic | `src/pipelines`, `src/agentic` | RAG, GraphRAG, harness, agents |
| C — Eval/App | `src/eval`, `src/app`, `scripts/` | judge, metrics, dashboard, validators |
`contracts.py` / `config.py` are changed by one agent at a time, announced in `PROGRESS.md`. Merge branches at gates.

## 4. Suggested 7-day plan (Oct 1 → Oct 7)
| Day | Focus | Exit gate |
|---|---|---|
| 1 | Setup, Phase 0 (recon, scaffold, smoke tests, graphrag spike), start Phase 1 | Connections + dataset documented + splits |
| 2 | Phase 1 ingestion/graph + Phase 2 baselines (RAG, GraphRAG) + eval runner & judge | Baseline numbers on val; judge spot-check |
| 3 | Phase 3 agentic core (harness, orchestrator, agents, stop rules, behaviour tests) | Agent runs on dev; strategy change demonstrated |
| 4 | Phase 4: full 3-way bench, error analysis, tuning loop, agent-value analysis | Findings table with CIs; decide router (yes/no) |
| 5 | Phase 5 hidden-50 run + export; start Phase 6 temporal layer | Validated submission files; first conflict cases working |
| 6 | Phase 6 finish + Phase 7 dashboard, demo page, architecture diagram | Dashboard/demo run from clean clone |
| 7 (deadline day) | Hardening, demo video, writeup, README, final `make verify-all`, **submit early** | Submitted ≥ several hours before the cutoff |
If you fall behind: cut the router and extra dataset first, then reduce temporal scope to a smaller but well-evaluated conflict set. **Never cut the benchmark, traces or verification.**



## 5. How to talk to Antigravity (patterns that work)
- **Be outcome + evidence oriented:** "Implement X. Done when tests A, B pass and the trace for question Q shows a strategy change. Show output."
- **Ask for plans before code** on anything architectural; ask "what could go wrong?" and "how will you verify?" in the plan.
- **Constrain scope:** "Touch only `src/agentic/*` and its tests."
- **Use artifacts as contracts:** approve the Implementation Plan, then compare to the Walkthrough.
- **Resume cleanly:** new chat per phase; first message = "Follow AGENT.md session start."
- **When stuck:** use `/diagnose` (LOOP_INSTRUCTIONS) rather than "try again".
- **Teach-back:** after each phase ask *"Explain the design, the 3 key trade-offs, and what a judge might challenge."* Keep answers in `docs/DECISIONS.md` — this is your Q&A prep (10% of score).

## 6. What to review yourself (don't fully delegate)
1. `contracts.py` (the shape of everything).
2. The judge prompt + 10 judged examples.
3. The orchestrator prompt and stop rules.
4. Token accounting path (gateway) — your headline numbers depend on it.
5. The final analysis claims: does each chart/claim follow from the data?
6. Secrets scan result before every push.

## 7. Quality gates before each merge to main
`make verify` green → relevant L4/L5 evidence attached → docs updated → no secrets → `PROGRESS.md` current.

## 8. Submission checklist (final day)
- [ ] GitHub repo public, README quickstart works from a clean clone (`clean_clone_check.sh`)
- [ ] `submission/` files for the 50 hidden questions validated (`make validate-submission`)
- [ ] Metrics dashboard: 3 pipelines × accuracy, completeness, tokens, latency, per-category, Pareto, agent lift with CIs
- [ ] Architecture diagram (Mermaid source + PNG/SVG in `docs/`)
- [ ] Demo video 3–5 min: problem → architecture → live 3-way comparison → agent trace → temporal conflict → key finding "when agents matter" → limitations
- [ ] Writeup: what built, how it works, key results, limitations, what next
- [ ] Social post (optional, tag @TigerGraph)
- [ ] `docs/DECISIONS.md` current; known limitations stated honestly
- [ ] Keys rotated/removed if they ever touched a commit; `.env` not in repo

## 9. Demo video outline (≈4 min)
0:00 hook: "Which questions actually need an agent?" · 0:20 architecture (one diagram) · 0:50 live: same question to RAG / GraphRAG / Agentic with token counters · 1:40 agent trace walkthrough (plan → tool choices → gap → strategy change → stop) · 2:30 benchmark dashboard & the headline finding · 3:15 temporal conflict demo (supersession + uncertainty) · 3:45 limitations & next steps.

## 10. Final-presentation Q&A prep (have crisp answers ready)
- Why is agentic worth (or not) its token cost? Show cost-per-correct and the Pareto plot.
- How do you avoid the agent looping or over-spending? Stop rules + behaviour tests.
- How do you know your judge is reliable? Calibration agreement number.
- How did you avoid overfitting to the 100 visible questions? Splits + hidden-50 policy.
- What fails? Show the failure taxonomy honestly.
- Why TigerGraph (native traversal + vectors in one engine)? Show a query that would be painful elsewhere.
