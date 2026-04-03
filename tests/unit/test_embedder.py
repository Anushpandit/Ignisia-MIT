from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from chunker import Chunk


class _FakeEmbeddingArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows
        self.shape = (len(rows), len(rows[0]) if rows else 0)

    def tolist(self) -> list[list[float]]:
        return self._rows


def _make_chunk(customer_id: str | None, source_file: str) -> Chunk:
    metadata = {
        "customer_id": customer_id,
        "source_file": source_file,
        "source_type": "pdf",
        "document_date": "2026-04-03",
        "block_type": "paragraph",
        "heading_context": "Page 1",
    }
    return Chunk(text=f"Chunk text for {source_file}", metadata=metadata)


class EmbedderTests(unittest.TestCase):
    def _import_embedder(self):
        model_mock = MagicMock()
        client_mock = MagicMock()

        sentence_transformers_module = types.ModuleType("sentence_transformers")
        chromadb_module = types.ModuleType("chromadb")

        sentence_transformers_module.SentenceTransformer = MagicMock(return_value=model_mock)
        chromadb_module.PersistentClient = MagicMock(return_value=client_mock)

        with patch.dict(
            sys.modules,
            {
                "sentence_transformers": sentence_transformers_module,
                "chromadb": chromadb_module,
            },
        ):
            sys.modules.pop("embedder", None)
            embedder = importlib.import_module("embedder")

        return embedder, model_mock, client_mock

    def test_embed_and_store_routes_chunks_to_customer_collections(self) -> None:
        embedder, model_mock, client_mock = self._import_embedder()
        collection_one = MagicMock()
        collection_two = MagicMock()
        client_mock.get_or_create_collection.side_effect = [collection_one, collection_two]
        model_mock.encode.return_value = _FakeEmbeddingArray(
            [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        )

        chunks = [
            _make_chunk("cust-001", "policy.pdf"),
            _make_chunk("cust-001", "quote.pdf"),
            _make_chunk("Acme Corp", "email.eml"),
        ]

        result = embedder.embed_and_store(chunks)

        self.assertEqual(result.total_chunks_received, 3)
        self.assertEqual(result.total_chunks_stored, 3)
        self.assertEqual(result.customers_processed, ["cust-001", "Acme Corp"])
        client_mock.get_or_create_collection.assert_any_call("customer_cust_001")
        client_mock.get_or_create_collection.assert_any_call("customer_acme_corp")
        collection_one.upsert.assert_called_once()
        collection_two.upsert.assert_called_once()
        model_mock.encode.assert_any_call(
            [chunk.text for chunk in chunks[:2]],
            batch_size=64,
            show_progress_bar=False,
        )

    def test_embed_and_store_empty_list(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()

        with self.assertLogs("embedder", level="WARNING"):
            result = embedder.embed_and_store([])

        self.assertEqual(result.total_chunks_received, 0)
        self.assertEqual(result.total_chunks_stored, 0)
        self.assertEqual(result.errors, [])

    def test_make_chunk_id_is_deterministic(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()
        chunk = Chunk(
            text="hello",
            metadata={
                "customer_id": "cust-001",
                "source_file": "refund policy.pdf",
                "block_type": "paragraph",
                "page": 3,
                "sub_chunk_index": 2,
            },
        )

        chunk_id = embedder._make_chunk_id(chunk, 9)

        self.assertEqual(
            chunk_id,
            "cust-001__refund_policy_pdf__paragraph__p3__i2",
        )

    def test_collection_name_sanitizes_inputs(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()

        self.assertEqual(embedder._collection_name("cust-001"), "customer_cust_001")
        self.assertEqual(embedder._collection_name("Acme Corp"), "customer_acme_corp")
        self.assertEqual(embedder._collection_name("  BIG-CO  "), "customer_big_co")

    def test_sanitize_metadata_makes_values_safe(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()
        metadata = {
            "none_value": None,
            "list_value": ["a", "b"],
            "dict_value": {"nested": 1},
            "string_value": "ok",
            "int_value": 5,
            "bool_value": True,
        }

        sanitized = embedder._sanitize_metadata(metadata)

        self.assertEqual(sanitized["none_value"], "")
        self.assertEqual(sanitized["list_value"], "['a', 'b']")
        self.assertEqual(sanitized["dict_value"], "{'nested': 1}")
        self.assertEqual(sanitized["string_value"], "ok")
        self.assertEqual(sanitized["int_value"], 5)
        self.assertEqual(sanitized["bool_value"], True)

    def test_group_chunks_by_customer(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()
        chunks = [
            _make_chunk("cust-a", "a.pdf"),
            _make_chunk("cust-b", "b.pdf"),
            _make_chunk("cust-a", "c.pdf"),
            _make_chunk("cust-c", "d.pdf"),
        ]

        grouped = embedder.group_chunks_by_customer(chunks)

        self.assertEqual(set(grouped.keys()), {"cust-a", "cust-b", "cust-c"})
        self.assertEqual([chunk.metadata["source_file"] for chunk in grouped["cust-a"]], ["a.pdf", "c.pdf"])

    def test_query_collection_missing_collection_returns_empty(self) -> None:
        embedder, _model_mock, client_mock = self._import_embedder()
        client_mock.get_collection.side_effect = Exception("missing")

        with self.assertLogs("embedder", level="WARNING"):
            results = embedder.query_collection("cust-404", "refund policy")

        self.assertEqual(results, [])

    def test_get_customer_stats_existing_and_missing(self) -> None:
        embedder, _model_mock, client_mock = self._import_embedder()
        existing_collection = MagicMock()
        existing_collection.count.return_value = 7

        def get_collection_side_effect(name: str):
            if name == "customer_cust_001":
                return existing_collection
            raise Exception("missing")

        client_mock.get_collection.side_effect = get_collection_side_effect

        existing = embedder.get_customer_stats("cust-001")
        missing = embedder.get_customer_stats("cust-999")

        self.assertEqual(existing["exists"], True)
        self.assertEqual(existing["chunk_count"], 7)
        self.assertEqual(missing["exists"], False)
        self.assertEqual(missing["chunk_count"], 0)

    def test_missing_customer_id_goes_to_unknown_group(self) -> None:
        embedder, _model_mock, _client_mock = self._import_embedder()
        chunks = [_make_chunk(None, "unknown.pdf")]

        with self.assertLogs("embedder", level="WARNING"):
            grouped = embedder.group_chunks_by_customer(chunks)

        self.assertEqual(list(grouped.keys()), ["unknown"])

    def test_query_collection_returns_query_results(self) -> None:
        embedder, model_mock, client_mock = self._import_embedder()
        collection = MagicMock()
        client_mock.get_collection.return_value = collection
        model_mock.encode.return_value = _FakeEmbeddingArray([[0.2, 0.4]])
        collection.query.return_value = {
            "ids": [["id-1"]],
            "documents": [["chunk text"]],
            "metadatas": [[{"source_file": "policy.pdf"}]],
            "distances": [[0.123]],
        }

        results = embedder.query_collection("cust-001", "refund policy", n_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "id-1")
        self.assertEqual(results[0].text, "chunk text")
        self.assertEqual(results[0].distance, 0.123)


if __name__ == "__main__":
    unittest.main()
