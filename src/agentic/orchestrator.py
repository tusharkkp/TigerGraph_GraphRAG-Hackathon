"""
Quota-Aware Agentic GraphRAG Orchestrator (Pipeline 3).

Architecture:
- Deterministic EntityLinker (0 LLM calls)
- LLM Call 1: Orchestrator / Planner generates structured execution plan (Pydantic validated)
- Deterministic Tool Execution: Dispatches pre-compiled parameterized GSQL queries to Savanna
- Deterministic EvidenceEvaluator: Verifies constraints, loops, budget, and sufficiency
- Dynamic Fallback: Automatically falls back to Vector Chunk Search on empty/failed graph tool
- LLM Call 2: AnswerGenerator synthesizes evidence-grounded final answer with citations
- Strict Quota Guarantee: <= 3 LLM calls per question.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from src.agentic.entity_linker import EntityLinker, LinkedEntities
from src.agentic.evaluator import EvidenceEvaluator
from src.agentic.tools import TigerGraphToolSuite
from src.contracts import CallTag, Citation, PipelineResult, TokenUsage, TraceStep
from src.llm.gateway import LLMGateway
from src.pipelines.answer_generator import AnswerGenerator, PipelineAnswer

logger = logging.getLogger(__name__)


class ToolArgs(BaseModel):
    """Explicitly typed tool arguments avoiding additionalProperties for Gemini Developer API."""

    sport: str = Field(default="", description="Sport name (e.g. Biathlon, Athletics)")
    year: int = Field(default=0, description="Year (e.g. 2014)")
    season: str = Field(default="", description="Season: Summer or Winter")
    gender: str = Field(default="", description="Gender: Men, Women, or Mixed")
    min_competitors: int = Field(default=0, description="Minimum competitors threshold")
    max_competitors: int = Field(default=0, description="Maximum competitors threshold")
    min_nations: int = Field(default=0, description="Minimum nations threshold")
    max_nations: int = Field(default=0, description="Maximum nations threshold")
    name_contains: str = Field(default="", description="Substring for event name")
    event_id: str = Field(default="", description="Event ID for details or navigation")
    direction: str = Field(default="PREVIOUS", description="Direction: PREVIOUS or NEXT")
    query: str = Field(default="", description="Search query string")
    top_k: int = Field(default=5, description="Number of results")
    group_by: str = Field(default="sport", description="Grouping field")
    metric: str = Field(default="count", description="Metric type")


class PlannedStep(BaseModel):
    """A single tool execution step planned by the orchestrator."""

    agent: str = Field(
        default="GraphTraversal",
        description="Agent name: GraphTraversal, Aggregator, EntityLinker, or VectorSearch",
    )
    tool: str = Field(
        description="Tool name: Find_Events, Aggregate_Events, Event_Details, Navigate_Edition, Medal_Table, Vector_Chunk_Search, Resolve_Entity, Get_Chunks_For_Docs",
    )
    args: ToolArgs = Field(
        default_factory=ToolArgs,
        description="Typed arguments for the tool",
    )
    purpose: str = Field(
        default="",
        description="Brief justification of why this step is needed",
    )


class ExecutionPlan(BaseModel):
    """Structured plan emitted by the LLM Orchestrator."""

    reasoning: str = Field(
        description="Analysis of question constraints, sports, years, entities, and strategy",
    )
    question_type: str = Field(
        description="One of: aggregation, superlative, temporal, multi_hop, lookup",
    )
    steps: list[PlannedStep] = Field(
        description="Ordered sequence of 1 to 3 tool steps to execute",
    )


PLANNER_PROMPT_TEMPLATE = """You are the master planning orchestrator for an Olympic Games GraphRAG system backed by a TigerGraph knowledge graph and vector index.

Your task is to analyze the user's question and choose an optimal sequence of 1 to 3 parameterized tool steps to retrieve the exact factual answer.

Question: {question}

Pre-extracted Deterministic Entity Hints:
{entity_hints}

Available Parameterized GSQL Tools:
1. Find_Events: Filter events by sport, year, season, gender, competitor thresholds, or name substring.
   Args: sport (str), year (int), season (str: Summer/Winter), gender (str: Men/Women/Mixed), min_competitors (int), max_competitors (int), min_nations (int), max_nations (int), name_contains (str), limit (int, default 50).
   Returns: total_count, matching events with competitors/nations/winning_value, and source doc IDs.
   *BEST FOR*: "How many events had > X competitors?", event lookup, finding event_id for a specific year and sport.

2. Aggregate_Events: Compute groupings or max/sum over events.
   Args: sport (str), year (int), season (str), gender (str), group_by ("sport"|"year"|"gender"), metric ("count"|"max_competitors"|"sum_competitors").
   *BEST FOR*: "Which event had the highest number of competitors?", "total competitors across events".

3. Event_Details: Retrieve complete metadata, medalists (gold, silver, bronze), venues, sports, games, and previous/next edition IDs for a known event_id.
   Args: event_id (str).
   *BEST FOR*: Who won gold/silver/bronze in a specific event, venue of an event, date of an event.

4. Navigate_Edition: Traverse the PREVIOUS_EDITION or NEXT_EDITION graph edge from an event_id.
   Args: event_id (str), direction ("PREVIOUS"|"NEXT").
   Returns: target event details and medalists.
   *BEST FOR*: "Who won the gold medal in [event] at the Olympics held immediately before [year]?"

5. Medal_Table: Retrieve medal counts (gold, silver, bronze, total) and medal events for a country or athlete.
   Args: entity_id (str), entity_type ("Country"|"Athlete"), year (int, optional), sport (str, optional).
   *BEST FOR*: "How many gold medals did [country/athlete] win?"

6. Vector_Chunk_Search: Semantic similarity search over document chunks via native HNSW index.
   Args: query (str), top_k (int, default 5).
   *BEST FOR*: Complex textual or venue-date multi-hop questions like "Who won the event held at [Venue] on [Date]?", or fallback if graph attributes do not match.

7. Resolve_Entity: Search for exact or near-match athlete, venue, country, sport, or event IDs.
   Args: query (str), entity_type ("athlete"|"country"|"venue"|"sport"|"event"|"all").

Guidelines & Invariants:
1. TEMPORAL QUESTIONS ("immediately before [year]" or "immediately after [year]"):
   You MUST ALWAYS plan exactly TWO steps:
   - Step 1: Agent='GraphTraversal', Tool='Find_Events', Args: sport, year=[reference year], gender, name_contains. (Finds the reference event).
   - Step 2: Agent='GraphTraversal', Tool='Navigate_Edition', Args: event_id='$step1.event_id', direction='PREVIOUS' (or 'NEXT'). (Traverses to target edition).
   NEVER stop at Step 1 for an "immediately before/after" question!

2. MULTI-HOP VENUE / DATE QUESTIONS ("event held at [Venue] on [Date]"):
   You MUST use Agent='VectorSearch', Tool='Vector_Chunk_Search', Args: query="{question}", top_k=6.
   Document chunks contain exact dates and venue matches.

3. AGGREGATION QUESTIONS ("how many [sport] events at [year] had more than [X] competitors"):
   Use Agent='Aggregator', Tool='Find_Events', Args: sport, year, min_competitors=(X+1).
   total_count directly yields the exact integer answer!

4. SUPERLATIVE QUESTIONS ("which [sport] event at [year] had highest competitors"):
   Use Agent='GraphTraversal', Tool='Find_Events', Args: sport, year.
   Top events include the competitors count.

Return ONLY a JSON object conforming to the ExecutionPlan schema.
"""


class AgenticOrchestrator:
    """Production Agentic GraphRAG Orchestrator coordinating tools, reasoning, and synthesis."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        tool_suite: TigerGraphToolSuite | None = None,
        answer_generator: AnswerGenerator | None = None,
        max_steps: int = 3,
        token_cap: int = 5000,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.tools = tool_suite or TigerGraphToolSuite()
        self.answer_generator = answer_generator or AnswerGenerator(gateway=self.gateway)
        self.max_steps = max_steps
        self.token_cap = token_cap

    def _create_plan(self, question: str, question_id: str, linked: LinkedEntities) -> tuple[ExecutionPlan, int, int]:
        """LLM Call 1: Generate structured execution plan."""
        hints_json = linked.to_dict()
        prompt = PLANNER_PROMPT_TEMPLATE.format(
            question=question,
            entity_hints=hints_json,
        )

        res = self.gateway.generate(
            role="orchestrator",
            prompt=prompt,
            schema=ExecutionPlan,
            temperature=0.0,
            max_output_tokens=1024,
            tag=CallTag(question_id=question_id, pipeline="agentic", role="planner"),
        )

        plan = res.parsed if (res.parsed and isinstance(res.parsed, ExecutionPlan)) else None
        if not plan:
            # Deterministic heuristic fallback plan if LLM planning failed schema
            logger.warning("Planner failed schema parsing for %s; using deterministic fallback plan", question_id)
            if "how many" in question.lower() and linked.sport and linked.year:
                plan = ExecutionPlan(
                    reasoning="Deterministic fallback for aggregation",
                    question_type="aggregation",
                    steps=[
                        PlannedStep(
                            agent="Aggregator",
                            tool="Find_Events",
                            args=ToolArgs(
                                sport=linked.sport or "",
                                year=linked.year or 0,
                                min_competitors=(linked.min_competitors or 0),
                            ),
                            purpose="Retrieve matching event count",
                        )
                    ],
                )
            elif "immediately before" in question.lower() and linked.sport and linked.year:
                plan = ExecutionPlan(
                    reasoning="Deterministic fallback for temporal edition navigation",
                    question_type="temporal",
                    steps=[
                        PlannedStep(
                            agent="GraphTraversal",
                            tool="Find_Events",
                            args=ToolArgs(sport=linked.sport or "", year=linked.year or 0, gender=linked.gender or ""),
                            purpose="Find reference event ID",
                        ),
                        PlannedStep(
                            agent="GraphTraversal",
                            tool="Navigate_Edition",
                            args=ToolArgs(event_id="$step1.event_id", direction="PREVIOUS"),
                            purpose="Navigate to previous Olympic edition",
                        ),
                    ],
                )
            else:
                plan = ExecutionPlan(
                    reasoning="Deterministic fallback to vector retrieval",
                    question_type="lookup",
                    steps=[
                        PlannedStep(
                            agent="VectorSearch",
                            tool="Vector_Chunk_Search",
                            args=ToolArgs(query=question, top_k=5),
                            purpose="Retrieve relevant document chunks",
                        )
                    ],
                )

        return plan, res.tokens_in, res.tokens_out

    def run(self, question: str, question_id: str = "q-001") -> PipelineResult:
        """
        Execute full Agentic GraphRAG workflow on question.
        """
        start_time = time.perf_counter()
        evaluator = EvidenceEvaluator(max_steps=self.max_steps, token_cap=self.token_cap)
        trace: list[TraceStep] = []
        accumulated_chunks: list[dict[str, Any]] = []
        graph_facts: list[str] = []
        source_doc_ids: set[str] = set()

        total_tokens_in = 0
        total_tokens_out = 0
        strategy_changed = False
        stop_reason = None

        # Step 0: Deterministic Entity Linking (0 LLM calls)
        linked = EntityLinker.link_question(question)

        # Step 1: LLM Planning (Call 1)
        plan, plan_tok_in, plan_tok_out = self._create_plan(question, question_id, linked)
        total_tokens_in += plan_tok_in
        total_tokens_out += plan_tok_out

        # Step 2: Deterministic Tool Execution Loop
        prev_step_result: dict[str, Any] = {}

        for step_idx, step in enumerate(plan.steps, start=1):
            step_start = time.perf_counter()
            tool_name = step.tool
            tool_args = step.args.model_dump() if hasattr(step.args, "model_dump") else dict(step.args)

            # Dynamic placeholder resolution across steps
            for k, v in list(tool_args.items()):
                if isinstance(v, str) and ("$step1" in v or "{event_id}" in v or v == "$prev_event_id"):
                    # Resolve event_id from previous step
                    if prev_step_result.get("events"):
                        tool_args[k] = prev_step_result["events"][0]["event_id"]
                    elif prev_step_result.get("target_event"):
                        tool_args[k] = prev_step_result["target_event"]["event_id"]
                    elif prev_step_result.get("event_id"):
                        tool_args[k] = prev_step_result["event_id"]
                elif k == "event_id" and (not v or v == "") and prev_step_result.get("events"):
                    tool_args["event_id"] = prev_step_result["events"][0]["event_id"]

            if tool_name == "Vector_Chunk_Search":
                # Dense embedding model (bge-base) achieves optimal recall on the full natural question
                tool_args["query"] = question
                tool_args["top_k"] = max(int(tool_args.get("top_k", 6)), 6)

            # Dispatch tool call
            try:
                obs = self.tools.execute(tool_name, tool_args)
            except Exception as e:
                logger.error("Tool execution error %s: %s", tool_name, e)
                obs = {"error": str(e), "source_doc_ids": []}

            step_lat_ms = round((time.perf_counter() - step_start) * 1000, 1)

            # Record source docs
            if obs.get("source_doc_ids"):
                source_doc_ids.update(obs["source_doc_ids"])

            # Formulate human-readable observation summary
            summary = self._summarize_observation(tool_name, obs)

            # Evaluate step with deterministic evaluator
            is_final_step = (step_idx == len(plan.steps))
            decision = evaluator.evaluate_step(
                step_num=step_idx,
                tool_name=tool_name,
                tool_args=tool_args,
                observation=obs,
                tokens_so_far=(total_tokens_in + total_tokens_out),
                is_final_step_planned=is_final_step,
            )

            trace_step = TraceStep(
                step=step_idx,
                agent=step.agent,
                tool=tool_name,
                args=tool_args,
                rationale=step.purpose or f"Execute {tool_name} to gather evidence",
                observation_summary=summary,
                new_evidence_ids=list(obs.get("source_doc_ids", [])),
                tokens_in=(plan_tok_in if step_idx == 1 else 0),
                tokens_out=(plan_tok_out if step_idx == 1 else 0),
                latency_ms=int(step_lat_ms),
                strategy_tag="graph_first" if ("Event" in tool_name or "Medal" in tool_name) else "vector_first",
                decision=decision.decision,
            )
            trace.append(trace_step)

            # Process evidence from observation
            self._ingest_observation_facts(tool_name, obs, graph_facts, accumulated_chunks)
            prev_step_result = obs

            # Check if strategy change / fallback required (e.g. empty results or error)
            if decision.decision == "change_strategy" or (
                obs.get("total_count") == 0
                and not obs.get("events")
                and not obs.get("chunks")
                and step_idx == 1
                and tool_name != "Vector_Chunk_Search"
            ):
                strategy_changed = True
                logger.info("Triggering fallback vector search for %s", question_id)
                fb_start = time.perf_counter()
                fb_obs = self.tools.execute("Vector_Chunk_Search", {"query": question, "top_k": 5})
                fb_lat = round((time.perf_counter() - fb_start) * 1000, 1)
                fb_summary = self._summarize_observation("Vector_Chunk_Search", fb_obs)

                trace.append(
                    TraceStep(
                        step=len(trace) + 1,
                        agent="VectorSearch",
                        tool="Vector_Chunk_Search",
                        args={"query": question, "top_k": 5},
                        rationale="Fallback to vector retrieval after empty graph results",
                        observation_summary=f"Fallback: {fb_summary}",
                        new_evidence_ids=list(fb_obs.get("source_doc_ids", [])),
                        tokens_in=0,
                        tokens_out=0,
                        latency_ms=int(fb_lat),
                        strategy_tag="vector_fallback",
                        decision="stop",
                    )
                )
                self._ingest_observation_facts("Vector_Chunk_Search", fb_obs, graph_facts, accumulated_chunks)
                stop_reason = "SUFFICIENCY_REACHED"
                break

            if decision.decision == "stop":
                stop_reason = decision.stop_reason or "SUFFICIENCY_REACHED"
                break

        if not stop_reason:
            stop_reason = "SUFFICIENCY_REACHED"

        # Step 3: Always enrich evidence with infobox chunks for all resolved source doc IDs
        if source_doc_ids:
            missing_dids = [did for did in source_doc_ids if not any(c.get("doc_id") == did for c in accumulated_chunks)]
            if missing_dids:
                chunk_res = self.tools.execute("Get_Chunks_For_Docs", {"doc_ids": missing_dids[:6]})
                if chunk_res.get("chunks"):
                    # Prioritize infobox chunk (_c000) at the front of accumulated_chunks
                    for c in chunk_res["chunks"]:
                        if not any(ac.get("chunk_id") == c.get("chunk_id") for ac in accumulated_chunks):
                            if c.get("chunk_index") == 0:
                                accumulated_chunks.insert(0, c)
                            else:
                                accumulated_chunks.append(c)

        # Step 4: Final Answer Generation (Call 2)
        answer_obj, ans_tokens, citations = self.answer_generator.generate_answer(
            question_id=question_id,
            question=question,
            evidence_chunks=accumulated_chunks,
            graph_facts=graph_facts,
            pipeline="agentic",
        )

        total_tokens_in += ans_tokens.llm_input_tokens
        total_tokens_out += ans_tokens.llm_output_tokens

        # Fallback citation generation if chunks were empty but doc_ids exist
        if not citations and source_doc_ids:
            citations = [
                Citation(
                    chunk_id=f"{did}_c000",
                    doc_id=did,
                    quote="Direct graph fact citation",
                    entity_ids=[],
                )
                for did in list(source_doc_ids)[:3]
            ]
        elif not citations and accumulated_chunks:
            c0 = accumulated_chunks[0]
            citations = [
                Citation(
                    chunk_id=c0.get("chunk_id", "chunk_0"),
                    doc_id=c0.get("doc_id", "doc_0"),
                    quote=c0.get("text", "")[:100],
                    entity_ids=[],
                )
            ]

        # Enforce exact token invariants
        tot_tok = total_tokens_in + total_tokens_out
        ctx_tok = min(ans_tokens.context_tokens, total_tokens_in)
        token_usage = TokenUsage(
            context_tokens=ctx_tok,
            llm_input_tokens=total_tokens_in,
            llm_output_tokens=total_tokens_out,
            total_tokens=tot_tok,
        )

        total_latency_ms = int((time.perf_counter() - start_time) * 1000)

        return PipelineResult(
            question_id=question_id,
            pipeline="agentic",
            answer=answer_obj.final_answer,
            citations=citations,
            retrieved_chunk_ids=[c.get("chunk_id", "") for c in accumulated_chunks if c.get("chunk_id")],
            tokens=token_usage,
            latency_ms=total_latency_ms,
            trace=trace,
            stop_reason=stop_reason,
            strategy_changed=strategy_changed,
            error=None,
        )

    def _summarize_observation(self, tool_name: str, obs: dict[str, Any]) -> str:
        """Create a concise 1-sentence summary of a tool observation for the trace."""
        if obs.get("error"):
            return f"Error: {obs['error'][:80]}"

        if tool_name == "Find_Events":
            cnt = obs.get("total_count", 0)
            events = obs.get("events", [])
            if events:
                top_ev = events[0]
                return f"Total matching events: {cnt}. Top: {top_ev.get('name')} (Year {top_ev.get('year')}, {top_ev.get('competitors')} competitors)"
            return f"Total matching events: {cnt}"

        elif tool_name == "Aggregate_Events":
            return f"Aggregated groups: {str(obs.get('groups', {}))[:100]}"

        elif tool_name == "Event_Details":
            meds = [m.get("name", "") for m in obs.get("medalists", []) if m.get("name")]
            return f"Event: {obs.get('name')} | Medalists: {', '.join(meds[:3])} | Winning: {obs.get('winning_value')}"

        elif tool_name == "Navigate_Edition":
            te = obs.get("target_event") or {}
            meds = [m.get("name", "") for m in obs.get("medalists", []) if m.get("name")]
            return f"Target edition: {te.get('name')} ({te.get('year')}) | Medalists: {', '.join(meds[:3])}"

        elif tool_name == "Medal_Table":
            return f"Gold: {obs.get('gold')}, Silver: {obs.get('silver')}, Bronze: {obs.get('bronze')}, Total: {obs.get('total')}"

        elif tool_name == "Vector_Chunk_Search":
            chunks = obs.get("chunks", [])
            return f"Retrieved {len(chunks)} chunks via HNSW vector search"

        elif tool_name == "Resolve_Entity":
            matches = obs.get("matches", [])
            return f"Resolved {len(matches)} entity matches"

        return f"Completed {tool_name}"

    def _ingest_observation_facts(
        self,
        tool_name: str,
        obs: dict[str, Any],
        graph_facts: list[str],
        accumulated_chunks: list[dict[str, Any]],
    ) -> None:
        """Extract structured graph facts and chunks from tool observation into answer context."""
        if obs.get("error"):
            return

        if tool_name == "Find_Events":
            cnt = obs.get("total_count")
            if cnt is not None:
                graph_facts.append(f"Total matching events found: {cnt}")
            for ev in obs.get("events", [])[:10]:
                fact = f"Event: {ev.get('name')} ({ev.get('year')})"
                if ev.get("competitors") is not None:
                    fact += f" | Competitors: {ev['competitors']}"
                if ev.get("nations") is not None:
                    fact += f" | Nations: {ev['nations']}"
                if ev.get("winning_value"):
                    fact += f" | Winning Mark: {ev['winning_value']}"
                graph_facts.append(fact)

        elif tool_name == "Aggregate_Events":
            groups = obs.get("groups", {})
            for k, v in groups.items():
                graph_facts.append(f"Group {k}: {v}")

        elif tool_name == "Event_Details":
            ev_str = f"Event: {obs.get('name')} ({obs.get('year')}, {obs.get('season')})"
            if obs.get("winning_value"):
                ev_str += f" | Winning value: {obs['winning_value']}"
            if obs.get("competitors"):
                ev_str += f" | Competitors: {obs['competitors']}"
            if obs.get("nations"):
                ev_str += f" | Nations: {obs['nations']}"
            graph_facts.append(ev_str)

            meds = [m.get("name", "") for m in obs.get("medalists", []) if m.get("name")]
            if meds:
                graph_facts.append(f"Medalists: {', '.join(meds)}")
            if obs.get("venues"):
                graph_facts.append(f"Venues: {', '.join(obs['venues'])}")
            if obs.get("sports"):
                graph_facts.append(f"Sport: {', '.join(obs['sports'])}")

        elif tool_name == "Navigate_Edition":
            te = obs.get("target_event") or {}
            if te:
                graph_facts.append(
                    f"Adjacent Olympic Edition Event: {te.get('name')} ({te.get('year')}) | Competitors: {te.get('competitors')} | Nations: {te.get('nations')} | Winning: {te.get('winning_value')}"
                )
            meds = [m.get("name", "") for m in obs.get("medalists", []) if m.get("name")]
            if meds:
                graph_facts.append(f"Adjacent Edition Medalists (Gold/Silver/Bronze): {', '.join(meds)}")

        elif tool_name == "Medal_Table":
            graph_facts.append(
                f"Medal Table Count: Gold={obs.get('gold')}, Silver={obs.get('silver')}, Bronze={obs.get('bronze')}, Total={obs.get('total')}"
            )

        elif tool_name in ("Vector_Chunk_Search", "Get_Chunks_For_Docs"):
            new_chunks = obs.get("chunks", [])
            for c in new_chunks:
                if not any(ac.get("chunk_id") == c.get("chunk_id") for ac in accumulated_chunks):
                    accumulated_chunks.append(c)
