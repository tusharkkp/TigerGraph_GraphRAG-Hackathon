"""Unit tests for Stage 1 deterministic structured infobox parser."""

from src.ingestion.structured_parser import (
    StructuredInfoboxParser,
    split_team_medalists,
)


class TestStructuredParser:
    def test_split_team_medalists(self):
        # 1. Single athlete
        res1 = split_team_medalists("Usain Bolt")
        assert len(res1) == 1
        assert res1[0] == ("Usain Bolt", 1.0)

        # 2. Concatenated camelCase team medalists (e.g. canoeing K-2)
        res2 = split_team_medalists("Rudolf DombiRoland Kökény")
        assert len(res2) == 2
        assert res2[0] == ("Rudolf Dombi", 0.9)
        assert res2[1] == ("Roland Kökény", 0.9)

        # 3. Comma-separated list
        res3 = split_team_medalists("Fernando Pimenta, Emanuel Silva")
        assert len(res3) == 2
        assert res3[0] == ("Fernando Pimenta", 1.0)
        assert res3[1] == ("Emanuel Silva", 1.0)

    def test_parse_individual_swimming_event(self):
        doc = {
            "doc_id": "Q250187",
            "title": "Swimming at the 2008 Summer Olympics – Men's 200 metre breaststroke",
            "text": """[Infobox Olympic event]
  event: Men's 200 metre breaststroke
  games: 2008 Summer
  venue: Beijing National Aquatics Center
  date: August 12 to 14, 2008
  competitors: 53
  nations: 39
  win_value: 2:07.64
  gold: Kosuke Kitajima
  goldNOC: JPN
  silver: Brenton Rickard
  silverNOC: AUS
  bronze: Hugues Duboscq
  bronzeNOC: FRA
  prev: 2004
  next: 2012

The men's 200 metre breaststroke event took place at the Beijing National Aquatics Center.
""",
        }

        parsed = StructuredInfoboxParser.parse_document(doc)
        assert parsed is not None
        assert parsed.doc_id == "Q250187"
        assert parsed.event_name == "Men's 200 metre breaststroke"
        assert parsed.sport == "Swimming"
        assert parsed.year == 2008
        assert parsed.season == "Summer"
        assert parsed.gender == "Men"
        assert parsed.venue == "Beijing National Aquatics Center"
        assert parsed.competitors == 53
        assert parsed.nations == 39
        assert parsed.winning_value == "2:07.64"
        assert parsed.prev_year == 2004
        assert parsed.next_year == 2012

        # 3 Medals (Gold, Silver, Bronze)
        assert len(parsed.medals) == 3
        gold = [m for m in parsed.medals if m.medal == "Gold"][0]
        assert gold.athlete_name == "Kosuke Kitajima"
        assert gold.noc == "JPN"
        assert gold.country_name == "Japan"

    def test_parse_team_event_and_graph_builder(self):
        doc = {
            "doc_id": "Q303623",
            "title": "Canoeing at the 2012 Summer Olympics – Men's K-2 1000 metres",
            "text": """[Infobox Olympic event]
  event: Men's canoe sprint K-2 1,000 metres
  games: 2012 Summer
  venue: Eton Dorney
  competitors: 24
  nations: 12
  gold: Rudolf DombiRoland Kökény
  goldNOC: HUN
""",
        }

        parsed = StructuredInfoboxParser.parse_document(doc)
        assert parsed is not None
        assert parsed.competitors == 24
        assert parsed.nations == 12

        # Team medalists parsed into 2 individual athletes
        assert len(parsed.medals) == 2
        ath_names = [m.athlete_name for m in parsed.medals]
        assert "Rudolf Dombi" in ath_names
        assert "Roland Kökény" in ath_names
        assert parsed.medals[0].raw_team_string == "Rudolf DombiRoland Kökény"

        # Build graph elements
        elements = StructuredInfoboxParser.build_graph_elements(parsed)
        assert len(elements["Event"]) == 1
        assert len(elements["Games"]) == 1
        assert len(elements["Venue"]) == 1
        assert len(elements["Athlete"]) == 2
        assert len(elements["Country"]) >= 1

        # Check MEDALIST edges
        medalist_edges = [e for e in elements["edges"] if e[2] == "MEDALIST"]
        assert len(medalist_edges) == 2
        assert medalist_edges[0][5]["medal"] == "Gold"
        assert medalist_edges[0][5]["noc"] == "HUN"
        assert medalist_edges[0][5]["raw_team_string"] == "Rudolf DombiRoland Kökény"

    def test_non_infobox_returns_none(self):
        doc = {
            "doc_id": "Q12345",
            "title": "Some Olympic Film (1996)",
            "text": "[Infobox film]\n  title: The Great Run\n  director: John Doe",
        }
        assert StructuredInfoboxParser.parse_document(doc) is None
