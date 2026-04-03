from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Iterable

TEST_CASES_DIR = Path(__file__).resolve().parent
ROOT_DIR = TEST_CASES_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from chunker import Chunk, chunk_documents
from embedder import delete_customer_data, embed_and_store, get_customer_stats, query_collection
from parser import ParsedDocument, parse_document
from rag import ask


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CUSTOMER_ID = "001"
TEST_DATA_DIR = TEST_CASES_DIR / f"customer_{CUSTOMER_ID}"

POLICY_TEXT = """# Operations Policy Manual

Issued by: Ignisia Operations
Document owner: Support Team

Refund Policy

For bulk orders, customers may request a refund within 30 days of invoice date.
Refunds are processed after finance verification.
The policy applies to standard enterprise procurement orders handled by the operations desk.
Customers must submit the request in writing and include the order number, invoice copy, and reason for refund.
Approved refunds are returned through the original payment channel after internal review is complete.
Requests submitted after the deadline are normally rejected unless compliance or billing made an error.

Support Escalation

Priority incidents should be acknowledged within 4 business hours.
The support team should provide an update on next steps during the first response whenever possible.
Escalated incidents remain open until the customer confirms resolution or the duty manager closes the case.
"""

UPDATE_EMAIL = """From: operations.manager@example.com
To: support@example.com
Subject: Updated refund policy for bulk orders
Date: Fri, 03 Apr 2026 09:30:00 +0530
Message-ID: <ops-update-001@example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hello team,

Please note the updated customer policy effective immediately.

For bulk orders, the refund window is now 15 days from invoice date.
This replaces the older 30-day guidance in the operations policy manual.
Priority incidents should still be acknowledged within 4 business hours.

Regards,
Operations Manager
"""


def _write_test_documents() -> list[Path]:
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    policy_path = TEST_DATA_DIR / "operations-policy-2025-01-10.txt"
    email_path = TEST_DATA_DIR / "refund-update-2026-04-03.eml"

    policy_path.write_text(POLICY_TEXT, encoding="utf-8")
    email_path.write_text(UPDATE_EMAIL, encoding="utf-8")
    return [policy_path, email_path]


def _parse_documents(paths: list[Path]) -> list[ParsedDocument]:
    documents: list[ParsedDocument] = []
    for path in paths:
        parsed = parse_document(path, uploaded_at="2026-04-03T09:30:00+05:30")
        documents.append(parsed)
        print(f"\nParsed: {path.name}")
        print(f"  file_type: {parsed.file_type}")
        print(f"  sections: {len(parsed.sections)}")
        print(f"  warnings: {len(parsed.warnings)}")
    return documents


def _index_documents(documents: list[ParsedDocument]) -> None:
    existing = get_customer_stats(CUSTOMER_ID)
    if existing.get("exists"):
        delete_customer_data(CUSTOMER_ID)
        print(f"\nCleared existing collection for customer {CUSTOMER_ID}.")

    chunks = chunk_documents(documents, CUSTOMER_ID)
    chunks = _ensure_unique_chunk_indexes(chunks)
    print(f"\nChunking complete: {len(chunks)} chunks created.")
    for index, chunk in enumerate(chunks, start=1):
        print(
            f"  chunk {index}: source={chunk.metadata.get('source_file')} "
            f"type={chunk.metadata.get('block_type')} "
            f"date={chunk.metadata.get('document_date') or chunk.metadata.get('uploaded_at')}"
        )

    result = embed_and_store(chunks)
    print("\nEmbedding complete:")
    print(f"  received: {result.total_chunks_received}")
    print(f"  stored:   {result.total_chunks_stored}")
    print(f"  failed:   {result.failed_customers}")
    if result.errors:
        print("  errors:")
        for error in result.errors:
            print(f"    - {error}")

    stats = get_customer_stats(CUSTOMER_ID)
    print("\nChroma collection stats:")
    print(f"  collection_name: {stats.get('collection_name')}")
    print(f"  exists:          {stats.get('exists')}")
    print(f"  chunk_count:     {stats.get('chunk_count')}")


def _ensure_unique_chunk_indexes(chunks: Iterable[Chunk]) -> list[Chunk]:
    normalized_chunks: list[Chunk] = []
    seen_per_source: dict[tuple[str, str, str], int] = {}

    for chunk in chunks:
        metadata = dict(chunk.metadata)
        source_key = (
            str(metadata.get("source_file", "")),
            str(metadata.get("block_type", "")),
            str(metadata.get("page", "x")),
        )
        next_index = seen_per_source.get(source_key, 0)
        metadata["sub_chunk_index"] = next_index
        seen_per_source[source_key] = next_index + 1
        normalized_chunks.append(Chunk(text=chunk.text, metadata=metadata))

    return normalized_chunks


def _preview_retrieval(question: str) -> None:
    results = query_collection(CUSTOMER_ID, question, n_results=3)
    print("\nTop retrieval matches:")
    if not results:
        print("  (none)")
        return

    for index, result in enumerate(results, start=1):
        metadata = result.metadata or {}
        print(f"  [{index}] source={metadata.get('source_file')} distance={result.distance:.4f}")
        print(
            f"      date={metadata.get('document_date') or metadata.get('uploaded_at')} "
            f"section={metadata.get('heading_context') or metadata.get('block_type')}"
        )
        snippet = " ".join(result.text.split())
        print(f"      text={snippet[:140]}{'...' if len(snippet) > 140 else ''}")


def run_pipeline() -> None:
    print(f"Preparing test corpus for customer {CUSTOMER_ID}...")
    paths = _write_test_documents()
    documents = _parse_documents(paths)
    _index_documents(documents)

    print("\nInteractive RAG test")
    print("Type a question and press Enter.")
    print("Type 'exit' to stop.\n")

    while True:
        question = input("Question: ").strip()
        if not question:
            print("Please enter a question.")
            continue
        if question.lower() in {"exit", "quit"}:
            print("Exiting pipeline test.")
            break

        _preview_retrieval(question)
        response = ask(customer_id=CUSTOMER_ID, question=question)

        print("\nAnswer:")
        print(response.answer)
        print()
        print(response.sources_display)
        if response.conflict.detected:
            print("\nConflict explanation:")
            print(f"  trusted_file: {response.conflict.trusted_file}")
            print(f"  trusted_date: {response.conflict.trusted_date}")
            print(f"  details:      {response.conflict.explanation}")
        print()


if __name__ == "__main__":
    run_pipeline()
