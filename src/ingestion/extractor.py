"""
Entity and relationship extraction for the Olympic domain using LLMGateway.

Enforces schema constraints, canonical entity ID generation, and quote grounding.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from src.contracts import CallTag

if TYPE_CHECKING:
    from src.llm.gateway import LLMGateway

# Domain-specific ontology
ALLOWED_ENTITY_TYPES = {
    "Athlete",
    "Event",
    "Country",
    "Venue",
    "Games",
    "Sport",
    "Organization",
    "Medal",
}

ALLOWED_RELATION_TYPES = {
    "PARTICIPATED_IN",
    "WON_MEDAL",
    "HELD_AT",
    "PART_OF",
    "REPRESENTS",
    "COMPETED_AGAINST",
    "LOCATED_IN",
    "AFFILIATED_WITH",
}


def normalize_entity_name(name: str) -> str:
    """Normalize entity name for canonical ID generation."""
    # Decompose unicode accents and remove non-ascii diacritics
    norm = unicodedata.normalize("NFKD", name)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    # Remove special punctuation and lowercase
    norm = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    norm = re.sub(r"\s+", " ", norm)
    return norm


def generate_canonical_entity_id(entity_type: str, name: str) -> str:
    """Generate a stable, deterministic ID for an entity: {type}_{hash}."""
    norm_name = normalize_entity_name(name)
    h = hashlib.sha256(norm_name.encode("utf-8")).hexdigest()[:10]
    clean_type = entity_type.strip().lower()
    return f"{clean_type}_{h}"


class ExtractedEntity(BaseModel):
    """An entity discovered within a document chunk."""

    name: str = Field(description="Canonical or surface name of the entity")
    entity_type: str = Field(description="Category (Athlete, Event, Country, Venue, Games, Sport)")
    description: str = Field(default="", description="1-2 sentence description of entity role")
    aliases: list[str] = Field(default_factory=list, description="Alternative names, acronyms, or codes")


class ExtractedRelation(BaseModel):
    """A directed relationship between two entities."""

    source: str = Field(description="Source entity name")
    target: str = Field(description="Target entity name")
    relationship_type: str = Field(
        description="Type (PARTICIPATED_IN, WON_MEDAL, HELD_AT, PART_OF, REPRESENTS, COMPETED_AGAINST)"
    )
    description: str = Field(default="", description="Description of the factual connection")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    quote: str = Field(default="", description="Exact sentence or substring from text demonstrating the relationship")


class ExtractionResult(BaseModel):
    """Structured extraction output from a single chunk."""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


EXTRACTION_PROMPT_TEMPLATE = """You are a knowledge graph extractor for an Olympic Games knowledge base.
Analyze the following document chunk and extract key entities and factual relationships.

ALLOWED ENTITY TYPES:
- Athlete: Competitors and athletes (e.g., Usain Bolt, Michael Phelps)
- Event: Olympic competition events (e.g., Men's 100 metres, Women's K-2 500m)
- Country: Nations or NOC delegations (e.g., Jamaica, United States, Great Britain)
- Venue: Facilities and stadiums (e.g., London Aquatics Centre, Olympic Stadium)
- Games: Specific Olympic Games edition (e.g., 2012 Summer Olympics, 2018 Winter Olympics)
- Sport: Broader sport category (e.g., Athletics, Swimming, Canoeing)

ALLOWED RELATIONSHIP TYPES:
- PARTICIPATED_IN: Athlete or Country -> Event or Games
- WON_MEDAL: Athlete or Country -> Medal or Event
- HELD_AT: Event or Games -> Venue
- PART_OF: Event -> Sport or Games
- REPRESENTS: Athlete -> Country
- COMPETED_AGAINST: Athlete -> Athlete

RULES:
1. Extract only explicitly stated facts. Do not invent or extrapolate.
2. For each relation, provide a concise exact 'quote' from the chunk text demonstrating the fact.
3. Classify each entity into one of the allowed types.
4. Keep names concise (e.g., 'Jamaica', not 'the team from Jamaica').

DOCUMENT CHUNK:
{chunk_text}
"""


class EntityRelationshipExtractor:
    """Extracts entities and relations from document chunks using the configured LLM."""

    def __init__(self, gateway: LLMGateway) -> None:
        self.gateway = gateway

    def extract_from_chunk(self, chunk: dict[str, Any]) -> ExtractionResult:
        """Extract entities and relations for a single chunk."""
        chunk_text = chunk.get("text", "")
        if not chunk_text.strip():
            return ExtractionResult()

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(chunk_text=chunk_text)
        tag = CallTag(
            role="extract",
            question_id=chunk.get("doc_id"),
            step=chunk.get("chunk_index"),
        )

        res = self.gateway.generate(
            role="extract",
            prompt=prompt,
            schema=ExtractionResult,
            tag=tag,
        )

        if isinstance(res.parsed, ExtractionResult):
            return res.parsed
        return ExtractionResult()

    @staticmethod
    def build_graph_elements(
        chunk: dict[str, Any],
        extraction: ExtractionResult,
    ) -> dict[str, Any]:
        """
        Convert ExtractionResult into vertices and edges ready for TigerGraph upsert.

        Returns:
            {
                'entities': list of (entity_id, attrs),
                'mentions_edges': list of (chunk_id, entity_id, attrs),
                'relates_edges': list of (src_id, tgt_id, attrs),
            }
        """
        chunk_id = chunk["chunk_id"]
        entity_name_to_id: dict[str, str] = {}
        entities: list[tuple[str, dict[str, Any]]] = []
        mentions_edges: list[tuple[str, str, str, str, str, dict[str, Any]]] = []
        relates_edges: list[tuple[str, str, str, str, str, dict[str, Any]]] = []

        # 1. Process entities
        for ent in extraction.entities:
            ent_type = ent.entity_type if ent.entity_type in ALLOWED_ENTITY_TYPES else "Entity"
            ent_id = generate_canonical_entity_id(ent_type, ent.name)
            entity_name_to_id[ent.name.strip().lower()] = ent_id

            entities.append((
                ent_id,
                {
                    "name": ent.name.strip(),
                    "entity_type": ent_type,
                    "description": ent.description,
                    "aliases": ent.aliases,
                },
            ))

            # DocumentChunk -[MENTIONS]-> Entity
            mentions_edges.append((
                "DocumentChunk",
                chunk_id,
                "MENTIONS",
                "Entity",
                ent_id,
                {"weight": 1.0},
            ))

        # 2. Process relations
        for rel in extraction.relations:
            src_key = rel.source.strip().lower()
            tgt_key = rel.target.strip().lower()
            src_id = entity_name_to_id.get(src_key)
            tgt_id = entity_name_to_id.get(tgt_key)

            if src_id and tgt_id and src_id != tgt_id:
                rel_type = (
                    rel.relationship_type
                    if rel.relationship_type in ALLOWED_RELATION_TYPES
                    else "RELATES_TO"
                )
                relates_edges.append((
                    "Entity",
                    src_id,
                    "RELATES_TO",
                    "Entity",
                    tgt_id,
                    {
                        "relationship_type": rel_type,
                        "description": rel.description,
                        "weight": float(rel.weight),
                        "source_chunk_id": chunk_id,
                    },
                ))

        return {
            "entities": entities,
            "mentions_edges": mentions_edges,
            "relates_edges": relates_edges,
        }
