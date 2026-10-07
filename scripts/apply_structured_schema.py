"""
Apply additive structured schema change to TigerGraph Savanna.

Adds:
- Vertices: Event, Games, Athlete, Country, Venue, Sport
- Edges: MEDALIST, HELD_AT, PART_OF_GAMES, BELONGS_TO_SPORT, REPRESENTS,
         PREVIOUS_EDITION, NEXT_EDITION, DESCRIBES_EVENT
"""

import logging
from src.graph.client import TigerGraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def apply_structured_schema() -> None:
    client = TigerGraphClient()
    gname = client.settings.tg_graphname or "GraphRAG"

    logger.info("Applying additive structured schema change on %s...", gname)

    schema_gsql = f"""
USE GRAPH {gname}
DROP JOB add_structured_schema
CREATE SCHEMA_CHANGE JOB add_structured_schema FOR GRAPH {gname} {{
  // Structured Vertices
  ADD VERTEX Event(
    PRIMARY_ID event_id STRING,
    name STRING,
    year INT,
    season STRING,
    gender STRING,
    competitors INT,
    nations INT,
    winning_value STRING,
    start_date STRING,
    end_date STRING
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  ADD VERTEX Games(
    PRIMARY_ID games_id STRING,
    year INT,
    season STRING,
    city STRING
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  ADD VERTEX Athlete(
    PRIMARY_ID athlete_id STRING,
    name STRING,
    normalized_name STRING,
    aliases LIST<STRING>
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  ADD VERTEX Country(
    PRIMARY_ID country_id STRING,
    noc STRING,
    name STRING,
    normalized_name STRING
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  ADD VERTEX Venue(
    PRIMARY_ID venue_id STRING,
    name STRING
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  ADD VERTEX Sport(
    PRIMARY_ID sport_id STRING,
    name STRING
  ) WITH STATS="OUTDEGREE_BY_EDGETYPE", PRIMARY_ID_AS_ATTRIBUTE="true";

  // Structured Edges
  ADD UNDIRECTED EDGE MEDALIST(FROM Event, TO Athlete, medal STRING, noc STRING, raw_team_string STRING, split_confidence FLOAT);
  ADD UNDIRECTED EDGE HELD_AT(FROM Event, TO Venue);
  ADD UNDIRECTED EDGE PART_OF_GAMES(FROM Event, TO Games);
  ADD UNDIRECTED EDGE BELONGS_TO_SPORT(FROM Event, TO Sport);
  ADD UNDIRECTED EDGE REPRESENTS(FROM Athlete, TO Country);
  ADD DIRECTED EDGE PREVIOUS_EDITION(FROM Event, TO Event);
  ADD DIRECTED EDGE NEXT_EDITION(FROM Event, TO Event);
  ADD UNDIRECTED EDGE DESCRIBES_EVENT(FROM Document, TO Event);
}}
RUN SCHEMA_CHANGE JOB add_structured_schema
DROP JOB add_structured_schema
"""
    res = client.conn.gsql(schema_gsql)
    logger.info("Schema change response:\n%s", res)


if __name__ == "__main__":
    apply_structured_schema()
