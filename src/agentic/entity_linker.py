"""
EntityLinker: Deterministic entity and constraint extraction (0 LLM calls).

Extracts sports, years, seasons, genders, countries/NOCs, and medals
from question text using pre-compiled regex and normalized vocabularies.
"""

from __future__ import annotations

import re
from typing import Any

from src.utils.normalization import build_match_key

# Known Olympic sports from corpus
KNOWN_SPORTS = [
    "Athletics", "Swimming", "Fencing", "Judo", "Weightlifting", "Taekwondo",
    "Rowing", "Cycling", "Gymnastics", "Boxing", "Canoeing", "Sailing",
    "Shooting", "Wrestling", "Archery", "Badminton", "Basketball", "Handball",
    "Hockey", "Table tennis", "Tennis", "Volleyball", "Triathlon", "Equestrian",
    "Diving", "Synchronized swimming", "Water polo", "Modern pentathlon",
    "Cross-country skiing", "Alpine skiing", "Biathlon", "Figure skating",
    "Speed skating", "Short-track speed skating", "Bobsleigh", "Luge", "Skeleton",
    "Ski jumping", "Nordic combined", "Freestyle skiing", "Snowboarding", "Curling",
]

# Known NOC codes and full country names
NOC_MAP = {
    "USA": "United States", "JAM": "Jamaica", "GBR": "Great Britain",
    "FRA": "France", "GER": "Germany", "ITA": "Italy", "CHN": "China",
    "RUS": "Russia", "AUS": "Australia", "JPN": "Japan", "CAN": "Canada",
    "NED": "Netherlands", "KOR": "South Korea", "ESP": "Spain", "BRA": "Brazil",
    "POL": "Poland", "CUB": "Cuba", "HUN": "Hungary", "KEN": "Kenya",
    "NOR": "Norway", "SWE": "Sweden", "FIN": "Finland", "SUI": "Switzerland",
}


class LinkedEntities:
    """Structured container for entities extracted from a question."""

    def __init__(
        self,
        sport: str | None = None,
        year: int | None = None,
        season: str | None = None,
        gender: str | None = None,
        noc: str | None = None,
        country: str | None = None,
        medal: str | None = None,
        event_query: str | None = None,
        min_competitors: int | None = None,
        raw_names: list[str] | None = None,
    ) -> None:
        self.sport = sport
        self.year = year
        self.season = season
        self.gender = gender
        self.noc = noc
        self.country = country
        self.medal = medal
        self.event_query = event_query
        self.min_competitors = min_competitors
        self.raw_names = raw_names or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "sport": self.sport,
            "year": self.year,
            "season": self.season,
            "gender": self.gender,
            "noc": self.noc,
            "country": self.country,
            "medal": self.medal,
            "event_query": self.event_query,
            "min_competitors": self.min_competitors,
            "raw_names": self.raw_names,
        }


class EntityLinker:
    """Zero-LLM deterministic entity and parameter extractor."""

    @staticmethod
    def link_question(question: str) -> LinkedEntities:
        q_lower = question.lower()

        # 1. Year and Season
        year = None
        yr_m = re.search(r"\b(18\d\d|19\d\d|20\d\d)\b", question)
        if yr_m:
            year = int(yr_m.group(1))

        season = None
        if "summer" in q_lower:
            season = "Summer"
        elif "winter" in q_lower:
            season = "Winter"

        # 2. Gender
        gender = None
        if "women" in q_lower or "women's" in q_lower:
            gender = "Women"
        elif "men" in q_lower or "men's" in q_lower:
            gender = "Men"
        elif "mixed" in q_lower:
            gender = "Mixed"

        # 3. Sport
        sport = None
        for s in KNOWN_SPORTS:
            if s.lower() in q_lower:
                sport = s
                break

        # 4. Country / NOC
        noc = None
        country = None
        for code, cname in NOC_MAP.items():
            if cname.lower() in q_lower or re.search(rf"\b{code}\b", question, re.IGNORECASE):
                noc = code
                country = cname
                break

        # 5. Medal
        medal = None
        if "gold" in q_lower:
            medal = "Gold"
        elif "silver" in q_lower:
            medal = "Silver"
        elif "bronze" in q_lower:
            medal = "Bronze"

        # 6. Numerical thresholds (e.g. "more than 32 competitors")
        min_comp = None
        comp_m = re.search(r"(?:more than|greater than|over|exceeding)\s+(\d+)\s+competitors", q_lower)
        if comp_m:
            min_comp = int(comp_m.group(1)) + 1

        # 7. Candidate event query
        # Extract quoted substrings or trailing event terms
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", question)

        return LinkedEntities(
            sport=sport,
            year=year,
            season=season,
            gender=gender,
            noc=noc,
            country=country,
            medal=medal,
            min_competitors=min_comp,
            raw_names=quoted,
        )
