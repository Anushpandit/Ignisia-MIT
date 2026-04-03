from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Sequence, cast

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from parser import ParsedDocument


CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
MIN_CHUNK = 50

logger = logging.getLogger("chunker")
_encoding = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_encoding.encode(text or ""))


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=_count_tokens,
)


@dataclass(slots=True)
class Chunk:
    text: str
    metadata: dict


def chunk_document(doc: ParsedDocument, customer_id: str) -> List[Chunk]:
    chunks, _failed = _chunk_document_internal(doc, customer_id)
    return chunks


def chunk_documents(
    docs: List[ParsedDocument],
    customer_id: str,
) -> List[Chunk]:
    total_files = len(docs)
    successful_files = 0
    failed_filenames: list[str] = []
    all_chunks: list[Chunk] = []

    for doc in docs:
        chunks, failed = _chunk_document_internal(doc, customer_id)
        all_chunks.extend(chunks)

        filename = _source_file(doc)
        if failed:
            failed_filenames.append(filename)
        else:
            successful_files += 1

    logger.info(
        "Chunked %d files for customer '%s': %d successful, %d chunks produced, failed files=%s",
        total_files,
        customer_id,
        len(all_chunks),
        successful_files,
        failed_filenames,
    )
    return all_chunks


def group_chunks_by_source(chunks: List[Chunk]) -> dict[str, List[Chunk]]:
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        source_file = str(chunk.metadata.get("source_file", ""))
        grouped.setdefault(source_file, []).append(chunk)
    return grouped


def _chunk_document_internal(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    file_type = str(getattr(doc, "file_type", "unknown") or "unknown")
    chunks: list[Chunk] = []
    failed = False

    if _document_is_empty(doc):
        logger.warning("Empty document '%s' received for chunking.", filename)

    handlers: dict[str, Callable[[ParsedDocument, str], tuple[list[Chunk], bool]]] = {
        "pdf": _chunk_pdf,
        "text": _chunk_text,
        "email": _chunk_email,
        "spreadsheet": _chunk_spreadsheet,
        "image": _chunk_image,
    }

    handler = handlers.get(file_type)
    if handler is None:
        logger.warning("Unrecognized file type '%s' for '%s'.", file_type, filename)
        return [], True

    handler_chunks, handler_failed = handler(doc, customer_id)
    chunks.extend(handler_chunks)
    failed = failed or handler_failed

    attachments = cast(Sequence[object], getattr(doc, "attachments", []) or [])
    for attachment in attachments:
        parsed_attachment = getattr(attachment, "parsed", None)
        if parsed_attachment is None:
            fallback_chunks = _chunk_attachment_text_fallback(doc, attachment, customer_id)
            if fallback_chunks:
                chunks.extend(fallback_chunks)
                continue

            attachment_name = str(getattr(attachment, "filename", "unknown attachment"))
            logger.warning(
                "Attachment parsing failure for '%s' in '%s': parsed attachment document not available.",
                attachment_name,
                filename,
            )
            continue

        try:
            attachment_chunks, attachment_failed = _chunk_document_internal(
                cast(ParsedDocument, parsed_attachment),
                customer_id,
            )
        except Exception as exc:
            attachment_name = str(getattr(attachment, "filename", "unknown attachment"))
            logger.warning(
                "Attachment parsing failure for '%s' in '%s': %s",
                attachment_name,
                filename,
                exc,
            )
            failed = True
            continue

        chunks.extend(attachment_chunks)
        failed = failed or attachment_failed

    filtered_chunks, discard_count = _filter_small_chunks(chunks, filename)
    if discard_count:
        logger.debug(
            "Discarded %d chunks below MIN_CHUNK for '%s'.",
            discard_count,
            filename,
        )
        logger.warning(
            "Discarded %d chunks below MIN_CHUNK for '%s'.",
            discard_count,
            filename,
        )

    logger.info(
        "Processed '%s' (%s): %d chunks produced.",
        filename,
        file_type,
        len(filtered_chunks),
    )
    return filtered_chunks, failed


def _chunk_pdf(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    chunks: list[Chunk] = []

    try:
        sections = cast(Sequence[object], getattr(doc, "sections", []) or [])
        logger.info(
            "Processing PDF '%s' with %d sections.",
            filename,
            len(sections),
        )

        current_heading = ""
        for section in sections:
            title = _clean_text(str(getattr(section, "title", "") or ""))
            if title:
                current_heading = title

            section_text = _clean_text(str(getattr(section, "text", "") or ""))
            if not section_text:
                continue

            page = getattr(section, "page", None)
            split_texts = _split_if_needed(section_text)
            for index, split_text in enumerate(split_texts):
                metadata = _build_metadata(
                    doc,
                    customer_id,
                    block_type="paragraph",
                    heading_context=current_heading,
                    page=page,
                    sub_chunk_index=index,
                )
                chunks.append(_make_chunk(split_text, metadata))
        return chunks, False
    except Exception as exc:
        logger.error("Failed to chunk '%s': %s", filename, exc)
        return chunks, True


def _chunk_text(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    chunks: list[Chunk] = []

    try:
        sections = [
            section
            for section in cast(Sequence[object], getattr(doc, "sections", []) or [])
            if _clean_text(str(getattr(section, "text", "") or ""))
        ]
        logger.info(
            "Processing text document '%s' with %d sections.",
            filename,
            len(sections),
        )

        window_size = 4
        overlap = 1
        step = max(1, window_size - overlap)

        for window_start in range(0, len(sections), step):
            window = sections[window_start : window_start + window_size]
            if not window:
                continue

            grouped_text = "\n".join(
                _clean_text(str(getattr(section, "text", "") or ""))
                for section in window
                if _clean_text(str(getattr(section, "text", "") or ""))
            ).strip()
            if not grouped_text:
                continue

            heading_context = _last_heading_from_sections(window)
            split_texts = _split_if_needed(grouped_text)
            for index, split_text in enumerate(split_texts):
                metadata = _build_metadata(
                    doc,
                    customer_id,
                    block_type="paragraph",
                    heading_context=heading_context,
                    window_start=window_start,
                    window_end=window_start + len(window) - 1,
                    sub_chunk_index=index,
                )
                chunks.append(_make_chunk(split_text, metadata))
        return chunks, False
    except Exception as exc:
        logger.error("Failed to chunk '%s': %s", filename, exc)
        return chunks, True


def _chunk_email(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    chunks: list[Chunk] = []

    try:
        body_text = _clean_text(str(getattr(doc, "text", "") or ""))
        sections = cast(Sequence[object], getattr(doc, "sections", []) or [])
        logger.info("Processing email '%s'.", filename)
        if not body_text:
            return chunks, False

        heading_context = _last_heading_from_sections(sections)
        metadata_sender = getattr(doc, "metadata", {}).get("sender", "")
        if not metadata_sender:
            sender_value = getattr(doc, "metadata", {}).get("from", "")
            metadata_sender = ", ".join(sender_value) if isinstance(sender_value, list) else str(sender_value)

        email_text = _compose_email_chunk_text(doc, body_text, sender=str(metadata_sender))
        split_texts = _split_if_needed(email_text)
        for index, split_text in enumerate(split_texts):
            metadata = _build_metadata(
                doc,
                customer_id,
                block_type="email_body",
                heading_context=heading_context,
                sender=str(metadata_sender),
                subject=str(getattr(doc, "metadata", {}).get("subject", "")),
                preserve_small_chunk=True,
                sub_chunk_index=index,
            )
            chunks.append(_make_chunk(split_text, metadata))
        return chunks, False
    except Exception as exc:
        logger.error("Failed to chunk '%s': %s", filename, exc)
        return chunks, True


def _chunk_spreadsheet(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    chunks: list[Chunk] = []

    try:
        tables = cast(Sequence[object], getattr(doc, "tables", []) or [])
        logger.info(
            "Processing spreadsheet '%s' with %d tables.",
            filename,
            len(tables),
        )

        for table_index, table in enumerate(tables):
            headers = _normalize_headers(getattr(table, "headers", []) or [])
            rows = cast(Sequence[Sequence[object]], getattr(table, "rows", []) or [])
            row_lines = [_serialize_table_row(headers, row) for row in rows]
            row_lines = [line for line in row_lines if line]
            if not row_lines:
                continue

            row_groups = _group_rows_by_token_limit(row_lines)
            for group_index, row_group in enumerate(row_groups):
                chunk_text = "\n".join(row_group)
                metadata = _build_metadata(
                    doc,
                    customer_id,
                    block_type="table",
                    heading_context=str(getattr(table, "name", "") or ""),
                    table_index=table_index,
                    sheet_name=str(getattr(table, "name", "") or ""),
                    sub_chunk_index=group_index,
                )
                chunks.append(_make_chunk(chunk_text, metadata))
        return chunks, False
    except Exception as exc:
        logger.error("Failed to chunk '%s': %s", filename, exc)
        return chunks, True


def _chunk_image(doc: ParsedDocument, customer_id: str) -> tuple[list[Chunk], bool]:
    filename = _source_file(doc)
    chunks: list[Chunk] = []

    try:
        image_text = _clean_text(str(getattr(doc, "text", "") or ""))
        sections = cast(Sequence[object], getattr(doc, "sections", []) or [])
        logger.info("Processing image '%s'.", filename)
        if not image_text:
            return chunks, False

        heading_context = _last_heading_from_sections(sections)
        split_texts = _split_if_needed(image_text)
        for index, split_text in enumerate(split_texts):
            metadata = _build_metadata(
                doc,
                customer_id,
                block_type="image_text",
                heading_context=heading_context,
                sub_chunk_index=index,
            )
            chunks.append(_make_chunk(split_text, metadata))
        return chunks, False
    except Exception as exc:
        logger.error("Failed to chunk '%s': %s", filename, exc)
        return chunks, True


def _build_metadata(
    doc: ParsedDocument,
    customer_id: str,
    *,
    block_type: str,
    heading_context: str,
    **extra: Any,
) -> dict[str, Any]:
    document_date = str(
        getattr(doc, "metadata", {}).get("date")
        or getattr(doc, "metadata", {}).get("sent_date", "")
    )
    metadata: dict[str, Any] = {
        "customer_id": customer_id,
        "source_file": _source_file(doc),
        "source_type": str(getattr(doc, "file_type", "")),
        "document_date": document_date,
        "uploaded_at": str(getattr(doc, "metadata", {}).get("uploaded_at", "")),
        "block_type": block_type,
        "heading_context": heading_context or "",
    }
    metadata.update(extra)
    return metadata


def _make_chunk(text: str, metadata: dict[str, Any]) -> Chunk:
    cleaned_text = text.strip()
    chunk = Chunk(text=cleaned_text, metadata=metadata)
    logger.debug(
        "Chunk tokens=%d heading='%s' page=%s sub_chunk_index=%s source='%s'",
        _count_tokens(cleaned_text),
        metadata.get("heading_context", ""),
        metadata.get("page"),
        metadata.get("sub_chunk_index"),
        metadata.get("source_file", ""),
    )
    return chunk


def _filter_small_chunks(chunks: Sequence[Chunk], filename: str) -> tuple[list[Chunk], int]:
    filtered: list[Chunk] = []
    discarded = 0

    for chunk in chunks:
        token_count = _count_tokens(chunk.text)
        if token_count < MIN_CHUNK and not bool(chunk.metadata.get("preserve_small_chunk")):
            discarded += 1
            logger.debug(
                "Discarding small chunk from '%s' with %d tokens.",
                filename,
                token_count,
            )
            continue
        filtered.append(chunk)

    return filtered, discarded


def _split_if_needed(text: str) -> list[str]:
    cleaned_text = text.strip()
    if not cleaned_text:
        return []
    if _count_tokens(cleaned_text) <= CHUNK_SIZE:
        return [cleaned_text]
    return [part.strip() for part in _splitter.split_text(cleaned_text) if part.strip()]


def _group_rows_by_token_limit(row_lines: Sequence[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current_group: list[str] = []
    current_text = ""

    for row_line in row_lines:
        candidate_text = row_line if not current_text else f"{current_text}\n{row_line}"
        if current_group and _count_tokens(candidate_text) > CHUNK_SIZE:
            groups.append(current_group)
            current_group = [row_line]
            current_text = row_line
            continue

        if not current_group and _count_tokens(row_line) > CHUNK_SIZE:
            logger.warning(
                "Spreadsheet row exceeds CHUNK_SIZE and will be emitted unsplit (%d tokens).",
                _count_tokens(row_line),
            )
            groups.append([row_line])
            current_group = []
            current_text = ""
            continue

        current_group.append(row_line)
        current_text = candidate_text

    if current_group:
        groups.append(current_group)
    return groups


def _serialize_table_row(headers: Sequence[str], row: Sequence[object]) -> str:
    values = [str(value).strip() for value in row]
    if not headers:
        return " | ".join(value for value in values if value)

    cells: list[str] = []
    for index, value in enumerate(values):
        if not value:
            continue
        header = headers[index] if index < len(headers) and headers[index] else f"Column {index + 1}"
        cells.append(f"{header}: {value}")
    return " | ".join(cells)


def _normalize_headers(headers: Sequence[object]) -> list[str]:
    return [str(header).strip() for header in headers]


def _last_heading_from_sections(sections: Sequence[object]) -> str:
    heading = ""
    for section in sections:
        title = _clean_text(str(getattr(section, "title", "") or ""))
        if title:
            heading = title
    return heading


def _source_file(doc: ParsedDocument) -> str:
    return str(getattr(doc, "metadata", {}).get("filename", ""))


def _document_is_empty(doc: ParsedDocument) -> bool:
    text = _clean_text(str(getattr(doc, "text", "") or ""))
    sections = getattr(doc, "sections", []) or []
    tables = getattr(doc, "tables", []) or []
    attachments = getattr(doc, "attachments", []) or []
    return not text and not sections and not tables and not attachments


def _clean_text(value: str) -> str:
    return value.strip()


def _compose_email_chunk_text(doc: ParsedDocument, body_text: str, *, sender: str) -> str:
    metadata = getattr(doc, "metadata", {})
    to_value = metadata.get("to", "")
    cc_value = metadata.get("cc", "")
    recipients = ", ".join(to_value) if isinstance(to_value, list) else str(to_value)
    cc_recipients = ", ".join(cc_value) if isinstance(cc_value, list) else str(cc_value)

    parts = [
        f"Subject: {str(metadata.get('subject', '')).strip()}",
        f"From: {sender.strip()}",
    ]
    if recipients.strip():
        parts.append(f"To: {recipients.strip()}")
    if cc_recipients.strip():
        parts.append(f"CC: {cc_recipients.strip()}")
    if str(metadata.get("date", "")).strip():
        parts.append(f"Date: {str(metadata.get('date', '')).strip()}")
    parts.append("")
    parts.append(body_text)
    return "\n".join(parts).strip()


def _chunk_attachment_text_fallback(
    parent_doc: ParsedDocument,
    attachment: object,
    customer_id: str,
) -> list[Chunk]:
    attachment_text = _clean_text(str(getattr(attachment, "text", "") or ""))
    if not attachment_text:
        return []

    attachment_filename = str(getattr(attachment, "filename", "") or "attachment")
    attachment_file_type = str(getattr(attachment, "file_type", "") or "unknown")
    attachment_content_type = str(getattr(attachment, "content_type", "") or "")
    attachment_metadata = cast(dict[str, Any], getattr(attachment, "metadata", {}) or {})
    attachment_date = str(
        attachment_metadata.get("date")
        or attachment_metadata.get("sent_date")
        or getattr(parent_doc, "metadata", {}).get("date")
        or getattr(parent_doc, "metadata", {}).get("sent_date", "")
    )
    attachment_uploaded_at = str(
        attachment_metadata.get("uploaded_at")
        or getattr(parent_doc, "metadata", {}).get("uploaded_at", "")
    )
    block_type = _attachment_block_type(attachment_file_type)
    split_texts = _split_if_needed(attachment_text)
    chunks: list[Chunk] = []

    for index, split_text in enumerate(split_texts):
        metadata = {
            "customer_id": customer_id,
            "source_file": attachment_filename,
            "source_type": attachment_file_type,
            "document_date": attachment_date,
            "uploaded_at": attachment_uploaded_at,
            "block_type": block_type,
            "heading_context": "",
            "parent_email_file": _source_file(parent_doc),
            "attachment_filename": attachment_filename,
            "attachment_file_type": attachment_file_type,
            "attachment_content_type": attachment_content_type,
            "preserve_small_chunk": True,
            "sub_chunk_index": index,
        }
        chunks.append(_make_chunk(split_text, metadata))

    return chunks


def _attachment_block_type(file_type: str) -> str:
    if file_type == "image":
        return "image_text"
    if file_type == "spreadsheet":
        return "table"
    if file_type == "email":
        return "email_body"
    return "paragraph"
