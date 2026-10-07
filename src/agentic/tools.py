"""
Parameterized GSQL Tool Suite for Agentic GraphRAG (Pipeline 3).

Dispatches strictly typed, pre-compiled GSQL queries to TigerGraph Savanna.
Contract Guarantee: Every tool returns a dictionary with:
- structured data (e.g. 'events', 'medalists', 'matches', 'total_count')
- 'source_doc_ids': list of document IDs for citations and provenance
- 'error': None or error message
"""

from __future__ import annotations

import logging
from typing import Any

from src.contracts import Citation
from src.graph.client import TigerGraphClient
from src.llm.embeddings import EmbeddingsService
from src.utils.normalization import build_match_key

logger = logging.getLogger(__name__)


class TigerGraphToolSuite:
    """Strongly typed wrapper around pre-compiled GSQL queries installed on TigerGraph Savanna."""

    def __init__(
        self,
        client: TigerGraphClient | None = None,
        embeddings: EmbeddingsService | None = None,
    ) -> None:
        self.client = client or TigerGraphClient()
        self.embeddings = embeddings or EmbeddingsService()

    def resolve_entity(
        self,
        query_term: str,
        entity_type: str = "all",
        limit_k: int = 5,
    ) -> dict[str, Any]:
        """
        Resolve a natural language entity to graph vertices (Athlete, Country, Venue, Sport, Event).
        """
        clean_q = query_term.strip()
        if not clean_q:
            return {"matches": [], "source_doc_ids": [], "error": "Empty query_term"}

        try:
            res = self.client.run_query(
                "Resolve_Entity",
                {"query_term": clean_q, "entity_type": entity_type, "limit_k": limit_k},
            )
        except Exception as e:
            logger.warning("Resolve_Entity failed: %s", e)
            return {"matches": [], "source_doc_ids": [], "error": str(e)}

        matches: list[dict[str, Any]] = []
        source_doc_ids: list[str] = []

        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                for k, v in block.items():
                    if isinstance(v, list):
                        for item in v:
                            vid = item.get("v_id")
                            vtype = item.get("v_type")
                            attrs = item.get("attributes", {})
                            name = (
                                attrs.get(f"{k}.name")
                                or attrs.get(f"{k}.normalized_name")
                                or vid
                            )
                            matches.append({
                                "id": vid,
                                "type": vtype,
                                "name": name,
                                "attributes": attrs,
                            })

        return {
            "matches": matches,
            "source_doc_ids": source_doc_ids,
            "error": None,
        }

    def find_events(
        self,
        sport_name: str = "",
        year_val: int = 0,
        season_val: str = "",
        gender_val: str = "",
        min_comp: int = 0,
        max_comp: int = 0,
        min_nat: int = 0,
        max_nat: int = 0,
        name_like: str = "",
        limit_k: int = 50,
    ) -> dict[str, Any]:
        """
        Query Event vertices with multi-dimensional filtering (sport, year, season, gender, competitor range).
        Returns total_count, matching events, and associated source doc IDs.
        """
        params = {
            "sport_name": sport_name.strip(),
            "year_val": int(year_val) if year_val else 0,
            "season_val": season_val.strip().capitalize() if season_val else "",
            "gender_val": gender_val.strip().capitalize() if gender_val else "",
            "min_comp": int(min_comp) if min_comp else 0,
            "max_comp": int(max_comp) if max_comp else 0,
            "min_nat": int(min_nat) if min_nat else 0,
            "max_nat": int(max_nat) if max_nat else 0,
            "limit_k": int(limit_k) if limit_k else 50,
        }

        try:
            res = self.client.run_query("Find_Events", params)
        except Exception as e:
            logger.warning("Find_Events failed: %s", e)
            return {"total_count": 0, "events": [], "source_doc_ids": [], "error": str(e)}

        total_count = 0
        events: list[dict[str, Any]] = []
        source_doc_ids: list[str] = []

        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                if "@@total_count" in block:
                    total_count = block["@@total_count"]
                if "Top" in block and isinstance(block["Top"], list):
                    for item in block["Top"]:
                        attrs = item.get("attributes", {})
                        ev_dict = {
                            "event_id": item.get("v_id"),
                            "name": attrs.get("Top.name"),
                            "year": attrs.get("Top.year"),
                            "season": attrs.get("Top.season"),
                            "gender": attrs.get("Top.gender"),
                            "competitors": attrs.get("Top.competitors"),
                            "nations": attrs.get("Top.nations"),
                            "winning_value": attrs.get("Top.winning_value"),
                        }
                        events.append(ev_dict)
                if "Docs" in block and isinstance(block["Docs"], list):
                    for d in block["Docs"]:
                        did = d.get("v_id")
                        if did and did not in source_doc_ids:
                            source_doc_ids.append(did)

        # Optional client-side substring filter for name_like
        if name_like.strip():
            target_sub = build_match_key(name_like.strip())
            filtered_events = []
            for ev in events:
                ev_name = build_match_key(ev.get("name") or "")
                if target_sub in ev_name:
                    filtered_events.append(ev)
            events = filtered_events
            total_count = len(filtered_events)

        return {
            "total_count": total_count,
            "events": events,
            "source_doc_ids": source_doc_ids,
            "error": None,
        }

    def aggregate_events(
        self,
        sport_name: str = "",
        year_val: int = 0,
        season_val: str = "",
        gender_val: str = "",
        group_by_field: str = "sport",
        metric_type: str = "count",
        limit_k: int = 10,
    ) -> dict[str, Any]:
        """
        Compute grouping and aggregations over Event vertices (count, max_competitors, sum_competitors).
        """
        params = {
            "sport_name": sport_name.strip(),
            "year_val": int(year_val) if year_val else 0,
            "season_val": season_val.strip().capitalize() if season_val else "",
            "gender_val": gender_val.strip().capitalize() if gender_val else "",
            "group_by_field": group_by_field.strip().lower() if group_by_field else "sport",
            "metric_type": metric_type.strip().lower() if metric_type else "count",
            "limit_k": int(limit_k) if limit_k else 10,
        }

        try:
            res = self.client.run_query("Aggregate_Events", params)
        except Exception as e:
            logger.warning("Aggregate_Events failed: %s", e)
            return {"groups": {}, "source_doc_ids": [], "error": str(e)}

        groups: dict[str, Any] = {}
        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                for k, v in block.items():
                    if k.startswith("@@group_") and isinstance(v, dict):
                        groups = v
                        break

        return {
            "groups": groups,
            "source_doc_ids": [],
            "error": None,
        }

    def event_details(self, event_id: str) -> dict[str, Any]:
        """
        Retrieve comprehensive metadata, medalists, venues, sports, and adjacent editions for an Event.
        """
        eid = event_id.strip()
        if not eid:
            return {"error": "Empty event_id", "source_doc_ids": []}

        try:
            res = self.client.run_query("Event_Details", {"event_id": eid})
        except Exception as e:
            logger.warning("Event_Details failed: %s", e)
            return {"error": str(e), "source_doc_ids": []}

        details: dict[str, Any] = {"event_id": eid}
        source_doc_ids: list[str] = []
        medalists: list[dict[str, Any]] = []
        venues: list[str] = []
        sports: list[str] = []
        games: list[str] = []
        prev_edition: dict[str, Any] | None = None
        next_edition: dict[str, Any] | None = None

        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                if "Ev" in block and block["Ev"]:
                    ev_item = block["Ev"][0]
                    attrs = ev_item.get("attributes", {})
                    details.update({
                        "name": attrs.get("Ev.name"),
                        "year": attrs.get("Ev.year"),
                        "season": attrs.get("Ev.season"),
                        "gender": attrs.get("Ev.gender"),
                        "competitors": attrs.get("Ev.competitors"),
                        "nations": attrs.get("Ev.nations"),
                        "winning_value": attrs.get("Ev.winning_value"),
                        "start_date": attrs.get("Ev.start_date"),
                        "end_date": attrs.get("Ev.end_date"),
                    })
                if "Docs" in block and isinstance(block["Docs"], list):
                    for d in block["Docs"]:
                        did = d.get("v_id")
                        if did and did not in source_doc_ids:
                            source_doc_ids.append(did)
                if "Medalists" in block and isinstance(block["Medalists"], list):
                    for m in block["Medalists"]:
                        attrs = m.get("attributes", {})
                        medalists.append({
                            "athlete_id": m.get("v_id"),
                            "name": attrs.get("Medalists.name"),
                            "normalized_name": attrs.get("Medalists.normalized_name"),
                        })
                if "Venues" in block and isinstance(block["Venues"], list):
                    for v in block["Venues"]:
                        attrs = v.get("attributes", {})
                        name = attrs.get("Venues.name")
                        if name:
                            venues.append(name)
                if "Sports" in block and isinstance(block["Sports"], list):
                    for s in block["Sports"]:
                        attrs = s.get("attributes", {})
                        name = attrs.get("Sports.name")
                        if name:
                            sports.append(name)
                if "GamesV" in block and isinstance(block["GamesV"], list):
                    for g in block["GamesV"]:
                        attrs = g.get("attributes", {})
                        yr = attrs.get("GamesV.year")
                        sn = attrs.get("GamesV.season")
                        city = attrs.get("GamesV.city")
                        games.append(f"{yr} {sn} ({city})")
                if "PrevE" in block and block["PrevE"]:
                    pe = block["PrevE"][0]
                    attrs = pe.get("attributes", {})
                    prev_edition = {
                        "event_id": pe.get("v_id"),
                        "name": attrs.get("PrevE.name"),
                        "year": attrs.get("PrevE.year"),
                    }
                if "NextE" in block and block["NextE"]:
                    ne = block["NextE"][0]
                    attrs = ne.get("attributes", {})
                    next_edition = {
                        "event_id": ne.get("v_id"),
                        "name": attrs.get("NextE.name"),
                        "year": attrs.get("NextE.year"),
                    }

        details["medalists"] = medalists
        details["venues"] = venues
        details["sports"] = sports
        details["games"] = games
        details["prev_edition"] = prev_edition
        details["next_edition"] = next_edition
        details["source_doc_ids"] = source_doc_ids
        details["error"] = None
        return details

    def navigate_edition(self, event_id: str, direction: str = "PREVIOUS") -> dict[str, Any]:
        """
        Traverse PREVIOUS_EDITION or NEXT_EDITION edge to retrieve adjacent edition details and medalists.
        """
        eid = event_id.strip()
        dir_clean = "NEXT" if direction.strip().upper() == "NEXT" else "PREVIOUS"

        try:
            res = self.client.run_query("Navigate_Edition", {"event_id": eid, "direction": dir_clean})
        except Exception as e:
            logger.warning("Navigate_Edition failed: %s", e)
            return {"error": str(e), "source_doc_ids": []}

        target_event: dict[str, Any] | None = None
        medalists: list[dict[str, Any]] = []
        source_doc_ids: list[str] = []

        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                if "TargetEv" in block and block["TargetEv"]:
                    te = block["TargetEv"][0]
                    attrs = te.get("attributes", {})
                    target_event = {
                        "event_id": te.get("v_id"),
                        "name": attrs.get("TargetEv.name"),
                        "year": attrs.get("TargetEv.year"),
                        "season": attrs.get("TargetEv.season"),
                        "competitors": attrs.get("TargetEv.competitors"),
                        "nations": attrs.get("TargetEv.nations"),
                        "winning_value": attrs.get("TargetEv.winning_value"),
                    }
                if "Medalists" in block and isinstance(block["Medalists"], list):
                    for m in block["Medalists"]:
                        attrs = m.get("attributes", {})
                        medalists.append({
                            "athlete_id": m.get("v_id"),
                            "name": attrs.get("Medalists.name"),
                        })
                if "Docs" in block and isinstance(block["Docs"], list):
                    for d in block["Docs"]:
                        did = d.get("v_id")
                        if did and did not in source_doc_ids:
                            source_doc_ids.append(did)

        return {
            "target_event": target_event,
            "medalists": medalists,
            "source_doc_ids": source_doc_ids,
            "error": None,
        }

    def medal_table(
        self,
        entity_id: str,
        entity_type: str = "Country",
        year_val: int = 0,
        sport_name: str = "",
    ) -> dict[str, Any]:
        """
        Compute medal counts (Gold, Silver, Bronze, Total) and retrieve medal events for Country or Athlete.
        """
        etype = "Athlete" if entity_type.strip().lower() == "athlete" else "Country"
        params = {
            "entity_id": entity_id.strip(),
            "entity_type": etype,
            "year_val": int(year_val) if year_val else 0,
            "sport_name": sport_name.strip(),
        }

        try:
            res = self.client.run_query("Medal_Table", params)
        except Exception as e:
            logger.warning("Medal_Table failed: %s", e)
            return {"error": str(e), "source_doc_ids": []}

        gold = 0
        silver = 0
        bronze = 0
        total = 0
        events: list[dict[str, Any]] = []
        source_doc_ids: list[str] = []

        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                if "@@gold_count" in block:
                    gold = block["@@gold_count"]
                if "@@silver_count" in block:
                    silver = block["@@silver_count"]
                if "@@bronze_count" in block:
                    bronze = block["@@bronze_count"]
                if "@@total_medals" in block:
                    total = block["@@total_medals"]
                if "MedalEvents" in block and isinstance(block["MedalEvents"], list):
                    for ev in block["MedalEvents"]:
                        attrs = ev.get("attributes", {})
                        events.append({
                            "event_id": ev.get("v_id"),
                            "name": attrs.get("MedalEvents.name"),
                            "year": attrs.get("MedalEvents.year"),
                            "season": attrs.get("MedalEvents.season"),
                        })
                if "Docs" in block and isinstance(block["Docs"], list):
                    for d in block["Docs"]:
                        did = d.get("v_id")
                        if did and did not in source_doc_ids:
                            source_doc_ids.append(did)

        return {
            "gold": gold,
            "silver": silver,
            "bronze": bronze,
            "total": total,
            "events": events,
            "source_doc_ids": source_doc_ids,
            "error": None,
        }

    def vector_search(self, query_text: str, top_k: int = 5) -> dict[str, Any]:
        """
        Embed query text and search native HNSW index in Savanna.
        """
        raw_vec = self.embeddings.embed_query(query_text)
        query_vec = [float(x) for x in raw_vec] if raw_vec else []
        if not query_vec:
            return {"chunks": [], "source_doc_ids": [], "error": "Empty query vector"}

        try:
            query_res = self.client.run_query(
                "Content_Similarity_Vector_Search",
                params={"query_vec": query_vec, "top_k": top_k},
            )
        except Exception as e:
            logger.warning("Vector search query failed: %s", e)
            return {"chunks": [], "source_doc_ids": [], "error": str(e)}

        if not query_res or not isinstance(query_res, list):
            return {"chunks": [], "source_doc_ids": [], "error": None}

        record = query_res[0]
        distances: dict[str, float] = record.get("@@distances", {})
        vertices: list[dict[str, Any]] = record.get("v", [])

        v_attrs: dict[str, dict[str, Any]] = {}
        source_doc_ids: list[str] = []

        for v in vertices:
            vid = v.get("v_id")
            attrs = v.get("attributes", {})
            if vid:
                doc_id = vid.rsplit("_c", 1)[0] if "_c" in vid else vid
                v_attrs[vid] = {
                    "chunk_id": vid,
                    "chunk_index": attrs.get("v.chunk_index", 0),
                    "text": attrs.get("v.text", ""),
                    "approx_tokens": attrs.get("v.approx_tokens", 0),
                    "doc_id": doc_id,
                }
                if doc_id not in source_doc_ids:
                    source_doc_ids.append(doc_id)

        sorted_pairs = sorted(distances.items(), key=lambda x: x[1])
        ranked_chunks = []
        for vid, dist in sorted_pairs[:top_k]:
            if vid in v_attrs:
                c = dict(v_attrs[vid])
                c["distance"] = dist
                ranked_chunks.append(c)

        return {
            "chunks": ranked_chunks,
            "source_doc_ids": source_doc_ids,
            "error": None,
        }

    def get_chunks_for_docs(self, doc_ids: list[str]) -> dict[str, Any]:
        """
        Retrieve all text chunks for specific Document IDs.
        """
        clean_dids = [d.strip() for d in doc_ids if d and d.strip()]
        if not clean_dids:
            return {"chunks": [], "source_doc_ids": [], "error": "Empty doc_ids"}

        try:
            res = self.client.run_query("Get_Chunks_For_Docs", {"doc_ids": clean_dids})
        except Exception as e:
            logger.warning("Get_Chunks_For_Docs failed: %s", e)
            return {"chunks": [], "source_doc_ids": clean_dids, "error": str(e)}

        chunks: list[dict[str, Any]] = []
        if isinstance(res, list):
            for block in res:
                if not isinstance(block, dict):
                    continue
                if "Chunks" in block and isinstance(block["Chunks"], list):
                    for c in block["Chunks"]:
                        cid = c.get("v_id")
                        attrs = c.get("attributes", {})
                        chunks.append({
                            "chunk_id": cid,
                            "chunk_index": attrs.get("Chunks.chunk_index", 0),
                            "text": attrs.get("Chunks.text", ""),
                            "approx_tokens": attrs.get("Chunks.approx_tokens", 0),
                            "doc_id": cid.rsplit("_c", 1)[0] if cid and "_c" in cid else cid,
                        })

        return {
            "chunks": chunks,
            "source_doc_ids": clean_dids,
            "error": None,
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Dynamic dispatcher mapping tool_name to the appropriate strongly typed method.
        """
        dispatch_map = {
            "Resolve_Entity": lambda a: self.resolve_entity(
                query_term=a.get("query_term", a.get("query", "")),
                entity_type=a.get("entity_type", "all"),
                limit_k=a.get("limit_k", a.get("limit", 5)),
            ),
            "Find_Events": lambda a: self.find_events(
                sport_name=a.get("sport_name", a.get("sport", "")),
                year_val=a.get("year_val", a.get("year", 0)),
                season_val=a.get("season_val", a.get("season", "")),
                gender_val=a.get("gender_val", a.get("gender", "")),
                min_comp=a.get("min_comp", a.get("min_competitors", 0)),
                max_comp=a.get("max_comp", a.get("max_competitors", 0)),
                min_nat=a.get("min_nat", a.get("min_nations", 0)),
                max_nat=a.get("max_nat", a.get("max_nations", 0)),
                name_like=a.get("name_like", a.get("name_contains", "")),
                limit_k=a.get("limit_k", a.get("limit", 50)),
            ),
            "Aggregate_Events": lambda a: self.aggregate_events(
                sport_name=a.get("sport_name", a.get("sport", "")),
                year_val=a.get("year_val", a.get("year", 0)),
                season_val=a.get("season_val", a.get("season", "")),
                gender_val=a.get("gender_val", a.get("gender", "")),
                group_by_field=a.get("group_by_field", a.get("group_by", "sport")),
                metric_type=a.get("metric_type", a.get("metric", "count")),
                limit_k=a.get("limit_k", a.get("limit", 10)),
            ),
            "Event_Details": lambda a: self.event_details(
                event_id=a.get("event_id", ""),
            ),
            "Navigate_Edition": lambda a: self.navigate_edition(
                event_id=a.get("event_id", ""),
                direction=a.get("direction", "PREVIOUS"),
            ),
            "Medal_Table": lambda a: self.medal_table(
                entity_id=a.get("entity_id", ""),
                entity_type=a.get("entity_type", "Country"),
                year_val=a.get("year_val", a.get("year", 0)),
                sport_name=a.get("sport_name", a.get("sport", "")),
            ),
            "Vector_Chunk_Search": lambda a: self.vector_search(
                query_text=a.get("query_text", a.get("query", "")),
                top_k=a.get("top_k", a.get("k", 5)),
            ),
            "Get_Chunks_For_Docs": lambda a: self.get_chunks_for_docs(
                doc_ids=a.get("doc_ids", []),
            ),
        }

        # Case-insensitive tool name lookup
        for known_name, fn in dispatch_map.items():
            if known_name.lower() == tool_name.strip().lower():
                try:
                    return fn(args)
                except Exception as e:
                    logger.error("Execution error in tool %s: %s", tool_name, e)
                    return {"error": str(e), "source_doc_ids": []}

        logger.warning("Unrecognized tool name: %s", tool_name)
        return {"error": f"Unknown tool: {tool_name}", "source_doc_ids": []}
