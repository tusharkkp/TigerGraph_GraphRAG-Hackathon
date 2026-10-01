"""Unit tests for TigerGraphClient — completely offline with mock connection."""

from unittest.mock import MagicMock

from src.graph.client import TigerGraphClient


class TestTigerGraphClient:
    def test_schema_summary_parsing(self):
        mock_conn = MagicMock()
        mock_conn.getSchema.return_value = {
            "VertexTypes": [
                {
                    "Name": "DocumentChunk",
                    "PrimaryId": {"AttributeName": "chunk_id"},
                    "Attributes": [{"AttributeName": "text"}, {"AttributeName": "approx_tokens"}],
                }
            ],
            "EdgeTypes": [
                {
                    "Name": "HAS_CHUNK",
                    "FromVertexTypeName": "Document",
                    "ToVertexTypeName": "DocumentChunk",
                    "IsDirectedEdge": True,
                }
            ],
        }

        client = TigerGraphClient(conn=mock_conn)
        summary = client.schema_summary()

        assert len(summary["vertices"]) == 1
        assert summary["vertices"][0]["name"] == "DocumentChunk"
        assert summary["vertices"][0]["primary_id"] == "chunk_id"
        assert "text" in summary["vertices"][0]["attributes"]

        assert len(summary["edges"]) == 1
        assert summary["edges"][0]["name"] == "HAS_CHUNK"
        assert summary["edges"][0]["from_vertex"] == "Document"
        assert summary["edges"][0]["to_vertex"] == "DocumentChunk"

    def test_upsert_vertices_formatting(self):
        mock_conn = MagicMock()
        mock_conn.upsertVertices.return_value = 2

        client = TigerGraphClient(conn=mock_conn)
        count = client.upsert_vertices(
            "DocumentChunk",
            [
                ("c1", {"text": "Chunk 1", "index": 0, "none_val": None}),
                ("c2", {"text": "Chunk 2", "index": 1}),
            ],
        )

        assert count == 2
        mock_conn.upsertVertices.assert_called_once()
        args = mock_conn.upsertVertices.call_args[0]
        assert args[0] == "DocumentChunk"
        # None values must be pruned
        assert "none_val" not in args[1][0][1]

    def test_upsert_edges_grouping(self):
        mock_conn = MagicMock()
        mock_conn.upsertEdges.return_value = 2

        client = TigerGraphClient(conn=mock_conn)
        count = client.upsert_edges(
            [
                ("Document", "doc1", "HAS_CHUNK", "DocumentChunk", "chunk1", {"weight": 1.0}),
                ("Document", "doc1", "HAS_CHUNK", "DocumentChunk", "chunk2", {"weight": 1.0}),
            ]
        )

        assert count == 2
        mock_conn.upsertEdges.assert_called_once_with(
            "Document", "HAS_CHUNK", "DocumentChunk",
            [("doc1", "chunk1", {"weight": 1.0}), ("doc1", "chunk2", {"weight": 1.0})],
        )

    def test_run_query(self):
        mock_conn = MagicMock()
        mock_conn.runInstalledQuery.return_value = [{"result": "ok"}]

        client = TigerGraphClient(conn=mock_conn)
        res = client.run_query("test_query", {"p": 10})

        assert res == [{"result": "ok"}]
        mock_conn.runInstalledQuery.assert_called_once_with("test_query", params={"p": 10})

    def test_auto_reauth_on_401(self):
        mock_conn = MagicMock()
        # First call fails with 401 unauthorized, second succeeds after refresh
        mock_conn.getVertexCount.side_effect = [
            Exception("401 Unauthorized token expired"),
            100,
        ]
        mock_conn.createSecret.return_value = "new_secret"
        mock_conn.getToken.return_value = ("new_token", 0)

        client = TigerGraphClient(conn=mock_conn)
        count = client.get_vertex_count("Document")

        assert count == 100
        mock_conn.createSecret.assert_called_once()
        mock_conn.getToken.assert_called_once_with("new_secret")
        assert mock_conn.apiToken == "new_token"
