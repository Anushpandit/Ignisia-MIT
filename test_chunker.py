from __future__ import annotations

import unittest
from unittest import mock

from parser import DocumentSection, DocumentTable, ParsedDocument

from chunker import (
    CHUNK_SIZE,
    Chunk,
    _count_tokens,
    _splitter,
    chunk_document,
    chunk_documents,
    group_chunks_by_source,
)


def _text_with_min_tokens(target_tokens: int, label: str) -> str:
    text = label
    while _count_tokens(text) < target_tokens:
        text = f"{text} {label}"
    return text


class ChunkerTests(unittest.TestCase):
    def test_pdf_chunking_splits_large_section(self) -> None:
        long_text = _text_with_min_tokens(CHUNK_SIZE + 180, "policy")
        short_one = _text_with_min_tokens(80, "overview")
        short_two = _text_with_min_tokens(90, "exceptions")
        document = ParsedDocument(
            file_type="pdf",
            text="",
            metadata={"filename": "refund_policy.pdf", "date": "2026-01-15"},
            sections=[
                DocumentSection(title="Overview", text=short_one, page=1),
                DocumentSection(title="Policy Body", text=long_text, page=2),
                DocumentSection(title="Exceptions", text=short_two, page=3),
            ],
        )

        chunks = chunk_document(document, "cust-123")

        expected_count = len(_splitter.split_text(long_text)) + 2
        self.assertEqual(len(chunks), expected_count)
        self.assertTrue(all(_count_tokens(chunk.text) <= CHUNK_SIZE for chunk in chunks))
        self.assertTrue(all(chunk.metadata["source_file"] == "refund_policy.pdf" for chunk in chunks))

    def test_spreadsheet_chunking_uses_table_block_type(self) -> None:
        row_value = _text_with_min_tokens(18, "widget")
        tables = [
            DocumentTable(
                name="Pricing",
                headers=["Product", "Price", "MOQ"],
                rows=[[row_value, "450", "100"] for _ in range(5)],
            ),
            DocumentTable(
                name="Discounts",
                headers=["Tier", "Discount"],
                rows=[["Gold", row_value] for _ in range(5)],
            ),
        ]
        document = ParsedDocument(
            file_type="spreadsheet",
            text="",
            metadata={"filename": "pricing.xlsx", "date": "2026-02-10"},
            tables=tables,
        )

        chunks = chunk_document(document, "cust-123")

        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(chunk.metadata["block_type"] == "table" for chunk in chunks))
        self.assertIn("Product:", chunks[0].text)
        self.assertIn("Tier:", chunks[1].text)

    def test_email_chunking_preserves_sender_and_subject(self) -> None:
        body = _text_with_min_tokens(90, "renewal")
        document = ParsedDocument(
            file_type="email",
            text=body,
            metadata={
                "filename": "renewal.eml",
                "date": "2026-03-12",
                "sender": "sales@example.com",
                "subject": "Renewal Terms",
            },
            sections=[DocumentSection(title="Plain Text Body", text=body, page=None)],
        )

        chunks = chunk_document(document, "cust-999")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["block_type"], "email_body")
        self.assertEqual(chunks[0].metadata["sender"], "sales@example.com")
        self.assertEqual(chunks[0].metadata["subject"], "Renewal Terms")

    def test_short_email_body_is_retained(self) -> None:
        document = ParsedDocument(
            file_type="email",
            text="Please review the attached quote before the call.",
            metadata={
                "filename": "note.eml",
                "date": "2026-03-12",
                "sender": "sales@example.com",
                "subject": "Quick note",
                "to": ["ops@example.com"],
            },
            sections=[DocumentSection(title="Plain Text Body", text="Please review the attached quote before the call.", page=None)],
        )

        chunks = chunk_document(document, "cust-999")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["block_type"], "email_body")
        self.assertIn("Subject: Quick note", chunks[0].text)

    def test_attachment_chunks_are_included(self) -> None:
        parent_text = _text_with_min_tokens(80, "parent")
        attachment_text = _text_with_min_tokens(90, "attachment")
        attachment_document = ParsedDocument(
            file_type="text",
            text=attachment_text,
            metadata={"filename": "appendix.txt", "date": "2026-03-10"},
            sections=[DocumentSection(title="Attachment", text=attachment_text, page=None)],
        )
        attachment = mock.Mock()
        attachment.filename = "appendix.txt"
        attachment.parsed = attachment_document

        document = ParsedDocument(
            file_type="email",
            text=parent_text,
            metadata={"filename": "source.eml", "date": "2026-03-09", "subject": "Source"},
            sections=[DocumentSection(title="Body", text=parent_text, page=None)],
            attachments=[attachment],
        )

        chunks = chunk_document(document, "cust-attach")

        source_files = {chunk.metadata["source_file"] for chunk in chunks}
        self.assertIn("source.eml", source_files)
        self.assertIn("appendix.txt", source_files)

    def test_attachment_text_fallback_is_chunked_without_parsed_document(self) -> None:
        attachment = mock.Mock()
        attachment.filename = "meeting-notes.txt"
        attachment.file_type = "text"
        attachment.content_type = "text/plain"
        attachment.text = "Budget approved and vendor shortlist ready."
        attachment.metadata = {}
        attachment.parsed = None

        document = ParsedDocument(
            file_type="email",
            text="Please review the attached notes.",
            metadata={"filename": "source.eml", "date": "2026-03-09", "subject": "Source"},
            sections=[DocumentSection(title="Body", text="Please review the attached notes.", page=None)],
            attachments=[attachment],
        )

        chunks = chunk_document(document, "cust-attach")

        attachment_chunks = [chunk for chunk in chunks if chunk.metadata["source_file"] == "meeting-notes.txt"]
        self.assertEqual(len(attachment_chunks), 1)
        self.assertEqual(attachment_chunks[0].metadata["parent_email_file"], "source.eml")
        self.assertEqual(attachment_chunks[0].metadata["block_type"], "paragraph")

    def test_small_chunks_are_filtered_out(self) -> None:
        small_text = _text_with_min_tokens(10, "small")
        document = ParsedDocument(
            file_type="text",
            text=small_text,
            metadata={"filename": "tiny.txt", "date": "2026-01-01"},
            sections=[DocumentSection(title="Tiny", text=small_text, page=None)],
        )

        chunks = chunk_document(document, "cust-123")

        self.assertEqual(chunks, [])

    def test_unknown_file_type_returns_empty_list(self) -> None:
        document = ParsedDocument(
            file_type="unknown",
            text="",
            metadata={"filename": "mystery.bin"},
        )

        chunks = chunk_document(document, "cust-123")

        self.assertEqual(chunks, [])

    def test_chunk_documents_keeps_sources_isolated(self) -> None:
        docs = [
            ParsedDocument(
                file_type="text",
                text="",
                metadata={"filename": "alpha.txt", "date": "2026-01-01"},
                sections=[DocumentSection(title="Alpha", text=_text_with_min_tokens(70, "ALPHA"), page=None)],
            ),
            ParsedDocument(
                file_type="text",
                text="",
                metadata={"filename": "beta.txt", "date": "2026-01-02"},
                sections=[DocumentSection(title="Beta", text=_text_with_min_tokens(70, "BETA"), page=None)],
            ),
            ParsedDocument(
                file_type="text",
                text="",
                metadata={"filename": "gamma.txt", "date": "2026-01-03"},
                sections=[DocumentSection(title="Gamma", text=_text_with_min_tokens(70, "GAMMA"), page=None)],
            ),
        ]

        chunks = chunk_documents(docs, "cust-multi")

        self.assertEqual({chunk.metadata["source_file"] for chunk in chunks}, {"alpha.txt", "beta.txt", "gamma.txt"})
        for chunk in chunks:
            if chunk.metadata["source_file"] == "alpha.txt":
                self.assertIn("ALPHA", chunk.text)
                self.assertNotIn("BETA", chunk.text)
                self.assertNotIn("GAMMA", chunk.text)
            if chunk.metadata["source_file"] == "beta.txt":
                self.assertIn("BETA", chunk.text)
                self.assertNotIn("ALPHA", chunk.text)
                self.assertNotIn("GAMMA", chunk.text)
            if chunk.metadata["source_file"] == "gamma.txt":
                self.assertIn("GAMMA", chunk.text)
                self.assertNotIn("ALPHA", chunk.text)
                self.assertNotIn("BETA", chunk.text)

    def test_group_chunks_by_source_groups_correctly(self) -> None:
        chunks = [
            Chunk(text="one", metadata={"source_file": "a.pdf"}),
            Chunk(text="two", metadata={"source_file": "b.pdf"}),
            Chunk(text="three", metadata={"source_file": "a.pdf"}),
        ]

        grouped = group_chunks_by_source(chunks)

        self.assertEqual(set(grouped.keys()), {"a.pdf", "b.pdf"})
        self.assertEqual([chunk.text for chunk in grouped["a.pdf"]], ["one", "three"])
        self.assertEqual([chunk.text for chunk in grouped["b.pdf"]], ["two"])

    def test_chunk_documents_continues_when_one_document_fails(self) -> None:
        good_document = ParsedDocument(
            file_type="text",
            text="",
            metadata={"filename": "good.txt", "date": "2026-01-01"},
            sections=[DocumentSection(title="Good", text=_text_with_min_tokens(70, "GOOD"), page=None)],
        )
        broken_document = mock.Mock()
        broken_document.file_type = "pdf"
        broken_document.text = ""
        broken_document.metadata = {"filename": "broken.pdf", "date": "2026-01-02"}
        broken_document.sections = object()
        broken_document.tables = []
        broken_document.attachments = []

        with self.assertLogs("chunker", level="ERROR") as captured_logs:
            chunks = chunk_documents([good_document, broken_document], "cust-safe")

        self.assertTrue(any("broken.pdf" in message for message in captured_logs.output))
        self.assertTrue(any(chunk.metadata["source_file"] == "good.txt" for chunk in chunks))
        self.assertFalse(any(chunk.metadata["source_file"] == "broken.pdf" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
