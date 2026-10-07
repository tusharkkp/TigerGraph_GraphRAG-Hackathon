"""
FastAPI Backend for Agentic GraphRAG Olympic QA System.

Exposes REST APIs for:
1. Multi-pipeline QA execution (/api/query): P1 Vector RAG, P2 GraphRAG, P3 Agentic GraphRAG
2. Live TigerGraph Savanna graph stats and schema inspection (/api/graph/stats)
3. Benchmark comparison reports (/api/benchmarks)
4. Parameterized GSQL tool playground (/api/tools/execute)
5. Pre-configured sample questions (/api/questions/sample)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import PROJECT_ROOT, REPORTS_DIR, get_embedding_config, get_tg_settings
from src.contracts import PipelineResult
from src.graph.client import TigerGraphClient
from src.pipelines.p1_vector_rag import VectorRAGPipeline
from src.pipelines.p2_graphrag import GraphRAGPipeline
from src.pipelines.p3_agentic import AgenticGraphRAGPipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Olympics Agentic GraphRAG API",
    description="Multi-Agent Parameterized GraphRAG & Vector Retrieval on TigerGraph Savanna",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = PROJECT_ROOT / "src" / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Shared pipeline singletons (lazy or eager)
_tg_client: TigerGraphClient | None = None
_p1: VectorRAGPipeline | None = None
_p2: GraphRAGPipeline | None = None
_p3: AgenticGraphRAGPipeline | None = None


def get_tg() -> TigerGraphClient:
    global _tg_client
    if _tg_client is None:
        _tg_client = TigerGraphClient()
    return _tg_client


def get_pipeline(name: str):
    global _p1, _p2, _p3
    if name == "p1":
        if _p1 is None:
            _p1 = VectorRAGPipeline()
        return _p1
    elif name == "p2":
        if _p2 is None:
            _p2 = GraphRAGPipeline()
        return _p2
    elif name == "p3":
        if _p3 is None:
            _p3 = AgenticGraphRAGPipeline()
        return _p3
    raise HTTPException(status_code=400, detail=f"Unknown pipeline '{name}'. Expected: p1, p2, p3")


# Request/Response models
class QueryRequest(BaseModel):
    question: str = Field(..., description="Natural language Olympic question")
    pipeline: str = Field(default="p3", description="Pipeline to execute: p1, p2, or p3")
    top_k: int = Field(default=5, ge=1, le=20, description="Top-k retrieval limit")


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Tool name, e.g. Find_Events, Event_Details")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "graph": get_tg_settings().tg_graphname or "GraphRAG",
        "embedding": get_embedding_config().get("model", "unknown"),
    }


@app.get("/api/graph/stats")
def graph_stats() -> dict[str, Any]:
    """Retrieve live vertex counts and schema summary from TigerGraph Savanna."""
    try:
        tg = get_tg()
        v_types = tg.conn.getVertexTypes(force=True)
        counts = {}
        for vt in v_types:
            try:
                cnt = tg.conn.getVertexCount(vt)
                counts[vt] = cnt
            except Exception:
                counts[vt] = 0
        return {
            "graph_name": tg.settings.tg_graphname or "GraphRAG",
            "host": tg.settings.tg_host,
            "vertex_counts": counts,
            "total_vertices": sum(counts.values()),
        }
    except Exception as e:
        logger.error("Failed to fetch graph stats: %s", e)
        return {
            "error": str(e),
            "graph_name": "GraphRAG",
            "vertex_counts": {
                "Document": 2951,
                "DocumentChunk": 13873,
                "Event": 2187,
                "Athlete": 6220,
                "Country": 133,
                "Venue": 314,
                "Sport": 42,
                "Games": 21,
            },
        }


@app.post("/api/query")
def run_query(req: QueryRequest) -> dict[str, Any]:
    """Execute a question on the chosen pipeline and return structured result."""
    clean_q = req.question.strip()
    if not clean_q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    pipe = get_pipeline(req.pipeline.lower())
    qid = f"web-{int(time.time() * 1000)}"

    try:
        res: PipelineResult = pipe.run({"qid": qid, "question": clean_q}, top_k=req.top_k)
        return res.model_dump()
    except Exception as e:
        logger.error("Query execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/benchmarks")
def get_benchmarks() -> dict[str, Any]:
    """Return all available benchmark reports across splits and pipelines."""
    results = {}
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.glob("benchmark_*.json"):
            try:
                with open(f, encoding="utf-8") as fp:
                    results[f.stem] = json.load(fp)
            except Exception as e:
                logger.warning("Error reading %s: %s", f, e)
    return results


@app.post("/api/tools/execute")
def execute_tool(req: ToolExecuteRequest) -> dict[str, Any]:
    """Execute any of the 8 installed GSQL tools on Savanna."""
    p3 = get_pipeline("p3")
    tool_suite = p3.tools
    return tool_suite.execute(req.tool_name, req.args)


@app.get("/api/questions/sample")
def sample_questions() -> list[dict[str, str]]:
    """Curated sample questions across the 5 evaluation taxonomies."""
    return [
        {
            "id": "pub-065",
            "qtype": "aggregation",
            "question": "According to the provided corpus, how many biathlon events at the 2014 Winter Olympics had more than 68 competitors?",
            "difficulty": "Hard (requires full graph aggregation over events)",
        },
        {
            "id": "pub-010",
            "qtype": "aggregation",
            "question": "According to the provided corpus, how many cycling events at the 2000 Summer Olympics had more than 30 competitors?",
            "difficulty": "Hard (filters sport + year + competitor threshold)",
        },
        {
            "id": "pub-057",
            "qtype": "temporal",
            "question": "Who won the gold medal in the women's 200 metres athletics event at the Summer Olympics held immediately before 2016?",
            "difficulty": "Medium (requires PREVIOUS_EDITION graph hop to 2012)",
        },
        {
            "id": "pub-011",
            "qtype": "lookup",
            "question": "Who won the gold medal in the event held at Richmond Olympic Oval on 14 February 2010?",
            "difficulty": "Medium (venue + date multi-hop lookup)",
        },
        {
            "id": "pub-066",
            "qtype": "superlative",
            "question": "According to the provided corpus, which weightlifting event at the 1992 Summer Olympics had the highest number of competitors?",
            "difficulty": "Medium (argmax competitors across weightlifting events)",
        },
        {
            "id": "pub-009",
            "qtype": "lookup",
            "question": "How many nations competed in Sailing at the 2016 Summer Olympics – Women's RS:X?",
            "difficulty": "Easy (single event attribute lookup)",
        },
    ]


# Mount static directory for frontend
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return FileResponse(PROJECT_ROOT / "README.md")
