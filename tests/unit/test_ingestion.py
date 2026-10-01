"""Unit tests for ingestion pipeline components — 100% offline with mocks."""

from pathlib import Path
from unittest.mock import MagicMock

from src.ingestion.chunker import TextChunker
from src.ingestion.extractor import (
    ChunkExtraction,
    EntityRelationshipExtractor,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    generate_canonical_entity_id,
    normalize_entity_name,
)
from src.ingestion.pipeline import IngestionPipeline


class TestChunker:
    def test_chunk_document_deterministic_ids(self):
        chunker = TextChunker(chunk_size=50, overlap_size=10)
        doc = {
            "doc_id": "Q12345",
            "title": "Canoeing at 2012 Summer Olympics",
            "text": "The Men's K-2 1000m took place on 8 August 2012 at Eton Dorney. " * 10,
        }

        chunks = chunker.chunk_document(doc)
        assert len(chunks) > 1
        assert chunks[0]["chunk_id"] == "Q12345_c000"
        assert chunks[1]["chunk_id"] == "Q12345_c001"
        assert chunks[0]["doc_id"] == "Q12345"
        assert chunks[0]["approx_tokens"] > 0

    def test_chunk_empty_document(self):
        chunker = TextChunker()
        doc = {"doc_id": "Q999", "text": "   "}
        chunks = chunker.chunk_document(doc)
        assert chunks == []

    def test_sibling_edges_generation(self):
        chunker = TextChunker()
        chunks = [
            {"chunk_id": "doc1_c000"},
            {"chunk_id": "doc1_c001"},
            {"chunk_id": "doc1_c002"},
        ]
        edges = chunker.get_sibling_edges(chunks)
        assert len(edges) == 2
        assert edges[0] == ("doc1_c000", "doc1_c001", {"weight": 1.0})
        assert edges[1] == ("doc1_c001", "doc1_c002", {"weight": 1.0})


class TestExtractor:
    def test_entity_normalization_and_id_generation(self):
        # Accents and case normalization
        name1 = "Émilie Fer"
        name2 = "emilie fer"
        assert normalize_entity_name(name1) == normalize_entity_name(name2)
        id1 = generate_canonical_entity_id("Athlete", name1)
        id2 = generate_canonical_entity_id("Athlete", name2)
        assert id1 == id2
        assert id1.startswith("athlete_")

    def test_build_graph_elements(self):
        chunk = {
            "chunk_id": "Q303623_c000",
            "doc_id": "Q303623",
            "text": "Usain Bolt won gold for Jamaica in the 100m at London 2012.",
        }

        extraction = ExtractionResult(
            entities=[
                ExtractedEntity(name="Usain Bolt", entity_type="Athlete"),
                ExtractedEntity(name="Jamaica", entity_type="Country"),
            ],
            relations=[
                ExtractedRelation(
                    source="Usain Bolt",
                    target="Jamaica",
                    relationship_type="REPRESENTS",
                    quote="won gold for Jamaica",
                )
            ],
        )

        elements = EntityRelationshipExtractor.build_graph_elements(chunk, extraction)

        # 2 Entities
        assert len(elements["entities"]) == 2
        entity_ids = [e[0] for e in elements["entities"]]
        assert any(eid.startswith("athlete_") for eid in entity_ids)
        assert any(eid.startswith("country_") for eid in entity_ids)

        # 2 MENTIONS edges from DocumentChunk -> Entity
        assert len(elements["mentions_edges"]) == 2
        assert elements["mentions_edges"][0][0] == "DocumentChunk"
        assert elements["mentions_edges"][0][1] == "Q303623_c000"
        assert elements["mentions_edges"][0][2] == "MENTIONS"

        # 1 RELATES_TO edge from Usain Bolt -> Jamaica
        assert len(elements["relates_edges"]) == 1
        rel = elements["relates_edges"][0]
        assert rel[0] == "Entity"
        assert rel[2] == "RELATES_TO"
        assert rel[5]["relationship_type"] == "REPRESENTS"
        assert rel[5]["source_chunk_id"] == "Q303623_c000"


class TestIngestionPipeline:
    def test_checkpoint_save_and_load(self, tmp_path: Path):
        cp_path = tmp_path / "checkpoint.json"
        pipeline = IngestionPipeline(
            gateway=MagicMock(),
            tg_client=MagicMock(),
            checkpoint_path=cp_path,
        )

        assert pipeline.load_checkpoint() == set()
        pipeline.save_checkpoint({"doc1", "doc2"})

        loaded = pipeline.load_checkpoint()
        assert loaded == {"doc1", "doc2"}

    def test_chunk_extraction_tokens_and_unpacking(self):
        extraction = ExtractionResult(
            entities=[ExtractedEntity(name="Paris", entity_type="Venue")],
            relations=[],
        )
        chunk_ext = ChunkExtraction(extraction, tokens_in=150, tokens_out=45)

        assert chunk_ext.tokens_in == 150
        assert chunk_ext.tokens_out == 45
        assert len(chunk_ext.entities) == 1
        assert chunk_ext.entities[0].name == "Paris"

        # Unpacking support
        res, t_in, t_out = chunk_ext
        assert res == extraction
        assert t_in == 150
        assert t_out == 45
