# Agentic GraphRAG Benchmark

> **TigerGraph × Gemini** — Three-way benchmark proving when agentic reasoning is worth its tokens.

## What This Is

Three pipelines answer the same 150 Olympic-domain questions:

| Pipeline | How It Works | When It Wins |
|----------|-------------|-------------|
| **RAG** | Vector similarity → top-k chunks → LLM answer | Simple lookups |
| **GraphRAG** | Entity linking → graph expansion → chunks → LLM answer | Structured multi-hop |
| **Agentic GraphRAG** | Autonomous investigation: plans, retrieves, evaluates, iterates | Complex reasoning + gaps |

The product is an **evidence-backed map** of which question types need an agent, with accuracy, completeness, token and latency numbers per pipeline.

## Quickstart

```bash
# 1. Clone
git clone https://github.com/<your-repo>/agentic-graphrag-benchmark.git
cd agentic-graphrag-benchmark

# 2. Configure
cp .env.example .env
# Edit .env with your TigerGraph Savanna + Gemini API credentials

# 3. Setup
python -m pip install -e ".[dev]"

# 4. Verify
make verify

# 5. Ingest corpus into TigerGraph
make ingest

# 6. Run benchmark
make bench ARGS="--pipelines rag graphrag agentic --split dev --limit 10"

# 7. Launch dashboard
make app
```

## Repository Layout

```
├── configs/           # models.yaml, retrieval.yaml, agent.yaml, eval.yaml
├── data/              # splits.json, processed/, README.md
├── Dataset/           # Raw corpus + questions (from hackathon)
├── docs/              # ARCHITECTURE.md, DECISIONS.md, PROGRESS.md, BLOCKERS.md
├── graph/             # schema.gsql, queries/*.gsql, migrations/
├── graphrag/          # TigerGraph GraphRAG reference (read-only)
├── reports/           # Generated analysis reports
├── results/           # Raw benchmark results (gitignored)
├── scripts/           # Utility scripts (splits, validation, export)
├── src/
│   ├── contracts.py   # Pydantic data contracts (PipelineResult, TokenUsage, etc.)
│   ├── config.py      # Centralised config loader
│   ├── llm/           # LLM Gateway (Gemini API, cache, retry, token accounting)
│   ├── graph/         # TigerGraph client and query management
│   ├── ingestion/     # Corpus → chunks → entities → relations → embeddings → graph
│   ├── pipelines/     # RAG and GraphRAG pipeline implementations
│   ├── agentic/       # Agent harness, orchestrator, specialised agents
│   ├── temporal/      # Temporal/conflict reasoning (stretch)
│   ├── eval/          # Runner, judge, metrics, stats, taxonomy
│   └── app/           # Streamlit dashboard and demo
├── submission/        # Hidden-50 output files
└── tests/             # unit/, integration/, contract/, behavior/
```

## Key Design Decisions

See [docs/DECISIONS.md](docs/DECISIONS.md) for all Architecture Decision Records.

## Stack

- **Graph + Vector DB:** TigerGraph Savanna (cloud)
- **LLM + Embeddings:** Gemini API (Google GenAI SDK)
- **Language:** Python 3.11+, pydantic v2
- **Dashboard:** Streamlit + Plotly
- **Testing:** pytest, ruff, mypy

## License

Code is MIT-licensed. Corpus text is derived from English Wikipedia ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)).
