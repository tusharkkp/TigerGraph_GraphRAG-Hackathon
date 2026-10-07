"""
Stage 1 Deterministic Structured Parser for Olympic Event Articles.

Parses [Infobox Olympic event] metadata into strongly-typed vertices and edges
with exact numerical attributes, dates, venues, sports, and medalists.
Zero LLM calls, 100% deterministic, executes across the corpus in seconds.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field

from src.utils.normalization import (
    build_match_key,
    clean_text_for_storage,
    replace_dash_context,
)

# Standard Olympic NOC (National Olympic Committee) 3-letter codes to Country Names
NOC_TO_COUNTRY: dict[str, str] = {
    "HUN": "Hungary",
    "USA": "United States",
    "GBR": "Great Britain",
    "GER": "Germany",
    "FRA": "France",
    "ITA": "Italy",
    "RUS": "Russia",
    "JPN": "Japan",
    "AUS": "Australia",
    "NED": "Netherlands",
    "CHN": "China",
    "KOR": "South Korea",
    "CAN": "Canada",
    "NOR": "Norway",
    "SWE": "Sweden",
    "CUB": "Cuba",
    "JAM": "Jamaica",
    "ESP": "Spain",
    "BRA": "Brazil",
    "KEN": "Kenya",
    "ETH": "Ethiopia",
    "POR": "Portugal",
    "GEO": "Georgia",
    "ARM": "Armenia",
    "TUR": "Turkey",
    "POL": "Poland",
    "CZE": "Czech Republic",
    "SVK": "Slovakia",
    "CRO": "Croatia",
    "SRB": "Serbia",
    "SLO": "Slovenia",
    "GRE": "Greece",
    "AUT": "Austria",
    "SUI": "Switzerland",
    "FIN": "Finland",
    "DEN": "Denmark",
    "NZL": "New Zealand",
    "RSA": "South Africa",
    "ARG": "Argentina",
    "MEX": "Mexico",
    "COL": "Colombia",
    "IRI": "Iran",
    "KAZ": "Kazakhstan",
    "UKR": "Ukraine",
    "BLR": "Belarus",
    "ROU": "Romania",
    "BUL": "Bulgaria",
    "EGY": "Egypt",
    "ALG": "Algeria",
    "MAR": "Morocco",
}


def split_team_medalists(text: str) -> list[tuple[str, float]]:
    """
    Split concatenated team medalist strings from infoboxes into individual athlete names.
    
    Returns list of (athlete_name, split_confidence):
    - Single athlete: confidence 1.0
    - Multi-name split: confidence 0.9
    """
    cleaned = clean_text_for_storage(text)
    if not cleaned:
        return []

    # If comma-separated or newline-separated
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        return [(p, 1.0) for p in parts]
    if "\n" in cleaned:
        parts = [p.strip() for p in cleaned.split("\n") if p.strip()]
        return [(p, 1.0) for p in parts]

    # Regex detecting camelCase boundary: lowercase letter followed directly by uppercase letter
    # Excludes Celtic name prefixes 'Mac' and 'Mc' (e.g. "MacLennan", "McDonald")
    # e.g. "Rudolf DombiRoland Kökény" -> "Rudolf Dombi" and "Roland Kökény"
    # Also handles accented unicode lowercase letters
    parts = re.split(r"(?<!\bMac)(?<!\bMc)(?<=[a-z\u00e0-\u017f])(?=[A-Z])", cleaned)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) > 1:
        # Verify that all split parts are plausible full names (at least have space or reasonable length)
        # If any part is an isolated fragment like single-word prefix/suffix, do not split
        return [(p, 0.9) for p in parts]
    return [(cleaned, 1.0)]


class ParsedMedalAward(BaseModel):
    """A medal awarded in an event."""

    medal: str  # Gold, Silver, Bronze
    athlete_name: str
    noc: str = ""
    country_name: str = ""
    raw_team_string: str = ""
    split_confidence: float = 1.0


class ParsedOlympicEvent(BaseModel):
    """Strongly-typed factual representation of an Olympic event from its infobox."""

    event_id: str
    doc_id: str
    event_name: str
    sport: str = ""
    games_id: str = ""
    year: int | None = None
    season: str = ""  # Summer, Winter
    gender: str = ""  # Men, Women, Mixed
    venue: str = ""
    competitors: int | None = None
    nations: int | None = None
    winning_value: str = ""
    raw_date: str = ""
    start_date: str = ""
    end_date: str = ""
    prev_year: int | None = None
    next_year: int | None = None
    medals: list[ParsedMedalAward] = Field(default_factory=list)


class StructuredInfoboxParser:
    """Extracts typed Olympic event entities and relations from document text."""

    @staticmethod
    def is_olympic_event_doc(doc: dict[str, Any]) -> bool:
        """Check if document has an [Infobox Olympic event] block."""
        text = doc.get("text", "")
        return "[Infobox Olympic event]" in text

    @classmethod
    def parse_document(cls, doc: dict[str, Any]) -> ParsedOlympicEvent | None:
        """Parse an Olympic event document into a ParsedOlympicEvent."""
        text = doc.get("text", "")
        if not cls.is_olympic_event_doc(doc):
            return None

        doc_id = doc.get("doc_id", "")
        title = doc.get("title", "")
        clean_title = clean_text_for_storage(title)

        # 1. Infer Sport from Title (e.g. "Canoeing at the 2012...", "Athletics at the 2008...")
        sport = ""
        sport_match = re.match(r"^(.*?)\s+at\s+the\s+\d{4}\s+(Summer|Winter)\s+Olympics", title)
        if sport_match:
            sport = clean_text_for_storage(sport_match.group(1).strip())

        # 2. Extract key-value lines from [Infobox Olympic event]
        fields: dict[str, str] = {}
        in_infobox = False
        for line in text.split("\n"):
            line_str = line.strip()
            if "[Infobox Olympic event]" in line_str:
                in_infobox = True
                continue
            if in_infobox:
                if line_str.startswith("[") and not line_str.startswith("[Infobox"):
                    # End of infobox block
                    break
                if not line.startswith("  ") and ":" not in line_str:
                    # Non-indented narrative text signals end of infobox
                    if line_str and not line_str.startswith("["):
                        break
                if ":" in line_str:
                    colon_idx = line_str.find(":")
                    k = line_str[:colon_idx].strip()
                    v = line_str[colon_idx + 1:].strip()
                    if k:
                        fields[k] = v

        # 3. Parse Event Name
        event_name = fields.get("event") or clean_title

        # 4. Parse Games, Year, and Season (Title takes precedence to correct infobox typos)
        games_str = fields.get("games", "")
        year: int | None = None
        season = ""
        games_match = re.search(r"(\d{4})\s*(Summer|Winter)", title)
        if not games_match:
            games_match = re.search(r"(\d{4})\s*(Summer|Winter)", games_str)

        if games_match:
            year = int(games_match.group(1))
            season = games_match.group(2)

        games_id = f"games_{year}_{season.lower()}" if year and season else ""

        # 5. Parse Gender
        gender = ""
        lower_name = (event_name + " " + title).lower()
        if "women" in lower_name:
            gender = "Women"
        elif "men" in lower_name:
            gender = "Men"
        elif "mixed" in lower_name:
            gender = "Mixed"

        # 6. Parse Competitors and Nations (Integers)
        competitors: int | None = None
        if "competitors" in fields:
            c_m = re.search(r"(\d+)", fields["competitors"])
            if c_m:
                val = int(c_m.group(1))
                # Outlier detection: if infobox has corrupted value > 5000 (e.g. 41000000 from template expansion),
                # extract true count from body text ("There were X competitors")
                if val > 5000:
                    text_m = re.search(r"[Tt]here were (\d+) competitors", doc.get("text", ""))
                    if text_m:
                        val = int(text_m.group(1))
                competitors = val

        nations: int | None = None
        if "nations" in fields:
            n_m = re.search(r"(\d+)", fields["nations"])
            if n_m:
                nations = int(n_m.group(1))

        # 7. Parse Venue
        venue = clean_text_for_storage(fields.get("venue", ""))

        # 8. Parse Dates
        raw_date = fields.get("date") or fields.get("dates") or ""
        clean_date = replace_dash_context(raw_date)

        # 9. Parse Winning Value
        win_value = clean_text_for_storage(fields.get("win_value", ""))

        # 10. Parse Prev and Next
        prev_year: int | None = None
        if "prev" in fields:
            p_m = re.search(r"(\d{4})", fields["prev"])
            if p_m:
                prev_year = int(p_m.group(1))

        next_year: int | None = None
        if "next" in fields:
            nx_m = re.search(r"(\d{4})", fields["next"])
            if nx_m:
                next_year = int(nx_m.group(1))

        # 11. Parse Medalists (Gold, Silver, Bronze)
        medals: list[ParsedMedalAward] = []
        for medal_type in ["gold", "silver", "bronze"]:
            name_val = fields.get(medal_type, "")
            noc_val = fields.get(f"{medal_type}NOC", "").upper().strip()
            country_name = NOC_TO_COUNTRY.get(noc_val, "")

            if name_val:
                split_athletes = split_team_medalists(name_val)
                for ath_name, conf in split_athletes:
                    medals.append(
                        ParsedMedalAward(
                            medal=medal_type.capitalize(),
                            athlete_name=ath_name,
                            noc=noc_val,
                            country_name=country_name,
                            raw_team_string=name_val,
                            split_confidence=conf,
                        )
                    )

        # Generate canonical event ID (including normalized sport and event name)
        # Use a plus-preserving normalizer: build_match_key strips '+',
        # which merges "+67 kg" with "67 kg" in Judo/Weightlifting/Taekwondo.
        def _norm_for_id(text: str) -> str:
            """Like build_match_key but preserves '+' (critical for weight classes)."""
            key = build_match_key(text)
            # Restore leading '+' if original had it
            stripped = text.strip()
            if stripped.startswith("+") or "+" in stripped.split()[0] if stripped else False:
                key = "plus " + key
            return key

        norm_sport = _norm_for_id(sport) if sport else "unknown"
        # For event_name, check for '+' in both the infobox event name AND
        # the document title (some infoboxes strip '+' from the event field).
        raw_event = event_name.strip()
        norm_event = build_match_key(event_name)
        title_str = doc.get("title", "")
        # Extract the event portion from the title (after "– " or "— ")
        title_event_part = ""
        for sep in ["–", "—", "-"]:
            if sep in title_str:
                title_event_part = title_str.split(sep, 1)[1].strip()
                break
        has_plus = "+" in raw_event or "+" in title_event_part
        if has_plus:
            norm_event = "plus_" + norm_event
        h = hashlib.sha256(f"{year}_{season}_{norm_sport}_{norm_event}".encode("utf-8")).hexdigest()[:10]
        event_id = f"event_{h}"

        return ParsedOlympicEvent(
            event_id=event_id,
            doc_id=doc_id,
            event_name=event_name,
            sport=sport,
            games_id=games_id,
            year=year,
            season=season,
            gender=gender,
            venue=venue,
            competitors=competitors,
            nations=nations,
            winning_value=win_value,
            raw_date=clean_date,
            prev_year=prev_year,
            next_year=next_year,
            medals=medals,
        )

    @classmethod
    def build_graph_elements(cls, parsed: ParsedOlympicEvent) -> dict[str, list[Any]]:
        """
        Convert ParsedOlympicEvent into TigerGraph vertices and edges matching schema v3.
        
        Returns:
            {
                'Event': list of (id, attrs),
                'Games': list of (id, attrs),
                'Venue': list of (id, attrs),
                'Sport': list of (id, attrs),
                'Athlete': list of (id, attrs),
                'Country': list of (id, attrs),
                'edges': list of (src_type, src_id, edge_type, tgt_type, tgt_id, attrs)
            }
        """
        elements: dict[str, list[Any]] = {
            "Event": [],
            "Games": [],
            "Venue": [],
            "Sport": [],
            "Athlete": [],
            "Country": [],
            "edges": [],
        }

        # 1. Event Vertex
        elements["Event"].append((
            parsed.event_id,
            {
                "name": parsed.event_name,
                "year": parsed.year or 0,
                "season": parsed.season,
                "gender": parsed.gender,
                "competitors": parsed.competitors or 0,
                "nations": parsed.nations or 0,
                "winning_value": parsed.winning_value,
                "start_date": parsed.start_date,
                "end_date": parsed.end_date,
            },
        ))

        # Edge Document -> Event
        if parsed.doc_id:
            elements["edges"].append((
                "Document", parsed.doc_id,
                "DESCRIBES_EVENT",
                "Event", parsed.event_id,
                {},
            ))

        # 2. Games Vertex & Edge
        if parsed.games_id and parsed.year:
            elements["Games"].append((
                parsed.games_id,
                {
                    "year": parsed.year,
                    "season": parsed.season,
                    "city": "",
                },
            ))
            elements["edges"].append((
                "Event", parsed.event_id,
                "PART_OF_GAMES",
                "Games", parsed.games_id,
                {},
            ))

        # 3. Venue Vertex & Edge
        if parsed.venue:
            venue_id = f"venue_{hashlib.sha256(build_match_key(parsed.venue).encode('utf-8')).hexdigest()[:10]}"
            elements["Venue"].append((
                venue_id,
                {"name": parsed.venue},
            ))
            elements["edges"].append((
                "Event", parsed.event_id,
                "HELD_AT",
                "Venue", venue_id,
                {},
            ))

        # 4. Sport Vertex & Edge
        if parsed.sport:
            sport_id = f"sport_{hashlib.sha256(build_match_key(parsed.sport).encode('utf-8')).hexdigest()[:10]}"
            elements["Sport"].append((
                sport_id,
                {"name": parsed.sport},
            ))
            elements["edges"].append((
                "Event", parsed.event_id,
                "BELONGS_TO_SPORT",
                "Sport", sport_id,
                {},
            ))

        # 5. Athletes, Countries & Medalist Edges
        for m in parsed.medals:
            ath_match_key = build_match_key(m.athlete_name)
            ath_id = f"athlete_{hashlib.sha256(ath_match_key.encode('utf-8')).hexdigest()[:10]}"

            elements["Athlete"].append((
                ath_id,
                {
                    "name": m.athlete_name,
                    "normalized_name": ath_match_key,
                    "aliases": [ath_match_key] if ath_match_key != m.athlete_name.lower() else [],
                },
            ))

            # Event -> Athlete (MEDALIST)
            elements["edges"].append((
                "Event", parsed.event_id,
                "MEDALIST",
                "Athlete", ath_id,
                {
                    "medal": m.medal,
                    "noc": m.noc,
                    "raw_team_string": m.raw_team_string,
                    "split_confidence": m.split_confidence,
                },
            ))

            # Country Vertex & Athlete -> Country (REPRESENTS)
            if m.noc:
                country_id = f"country_{m.noc.lower()}"
                country_name = m.country_name or m.noc
                elements["Country"].append((
                    country_id,
                    {
                        "noc": m.noc,
                        "name": country_name,
                        "normalized_name": build_match_key(country_name),
                    },
                ))
                elements["edges"].append((
                    "Athlete", ath_id,
                    "REPRESENTS",
                    "Country", country_id,
                    {},
                ))

        return elements
