# Demo Script (3–5 min)

## 0:00 — Hook (20s)
"Which questions actually need an AI agent? We built three pipelines and ran them on 150 Olympic trivia questions to find out."

## 0:20 — Architecture (30s)
Show the architecture diagram. Highlight:
- Same LLM gateway, same graph, same corpus for all three
- RAG = vector search only; GraphRAG = entity link + graph expansion; Agentic = autonomous investigation

## 0:50 — Live Demo: Same Question, Three Pipelines (50s)
**Easy question** (lookup): "How many nations competed in Men's foil fencing at the 1988 Olympics?"
- RAG: finds the right chunk, answers correctly. Fast. Cheap.
- GraphRAG: also correct, slightly more context from graph expansion.
- Agentic: also correct but 3x the tokens. **Overkill.**

## 1:40 — Agent Trace Walkthrough (50s)
**Hard question** (multi-hop): "Who won gold in the event held at Olympic Weightlifting Gymnasium on 20 Sep 1988?"
- Show the investigation trace: venue → event → athlete
- Highlight: strategy change when first retrieval found the venue but not the event
- Show evidence ledger building up

## 2:30 — Benchmark Dashboard (45s)
- Accuracy by question type: agent wins on multi-hop and temporal
- Pareto chart: accuracy vs tokens — where each pipeline sits
- Cost-per-correct answer comparison
- The headline finding: "Agents matter for X% of questions, costing Y% more tokens"

## 3:15 — Temporal Conflict Demo (30s) (if applicable)
Show a case where dates conflict between sources and the agent resolves it.

## 3:45 — Limitations & Next Steps (15s)
- Aggregation questions still hard (need exhaustive retrieval)
- Agent sometimes over-investigates simple questions
- Next: adaptive router that picks the cheapest sufficient pipeline
