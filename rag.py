from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, List

from embedder import QueryResult, query_collection

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

try:
    from groq import Groq
except ModuleNotFoundError:
    Groq = None

if load_dotenv is not None:
    load_dotenv()


logger = logging.getLogger("rag")

DEFAULT_MODEL = os.environ.get("RAG_MODEL", "llama-3.3-70b-versatile")
MAX_TOKENS = 1024
TEMPERATURE = 0.2
_OLDEST_POSSIBLE_DATE = datetime.min.replace(tzinfo=timezone.utc)
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")

if os.environ.get("GROQ_API_KEY") is None:
    logger.warning("GROQ_API_KEY is not set. rag.py can load, but Groq calls will fail.")
if load_dotenv is None:
    logger.warning(
        "python-dotenv is not installed. Install dependencies with uv sync to load .env automatically."
    )
if Groq is None:
    logger.warning("groq package is not installed. Install dependencies with uv sync before using rag.py.")

_groq_api_key = os.environ.get("GROQ_API_KEY")
_groq_client = Groq(api_key=_groq_api_key) if Groq is not None and _groq_api_key else None


@dataclass(slots=True)
class SourceReference:
    source_file: str
    page: str | int
    block_type: str
    heading_context: str
    document_date: str
    chunk_id: str
    distance: float
    uploaded_at: str = ""
    text_excerpt: str = ""


@dataclass(slots=True)
class ConflictInfo:
    detected: bool
    conflicting_files: List[str]
    trusted_file: str
    trusted_date: str
    explanation: str
    trusted_references: List[SourceReference] = field(default_factory=list)
    conflicting_references: List[SourceReference] = field(default_factory=list)


@dataclass(slots=True)
class RAGResponse:
    answer: str
    sources: List[SourceReference]
    conflict: ConflictInfo
    model_used: str
    chunks_used: int
    customer_id: str
    question: str
    sources_display: str


def ask(
    customer_id: str,
    question: str,
    n_results: int = 5,
    model: str = DEFAULT_MODEL,
    filters: dict | None = None,
) -> RAGResponse:
    try:
        return _run_rag(
            customer_id=customer_id,
            question=question,
            n_results=n_results,
            model=model,
            filters=filters,
            history=None,
        )
    except Exception as exc:
        logger.error(
            "Unexpected failure in ask() for customer '%s' question '%s': %s",
            customer_id,
            question,
            exc,
            exc_info=True,
        )
        return _error_response(
            customer_id=customer_id,
            question=question,
            model=model,
            answer="An unexpected error occurred while processing your question.",
        )


def ask_with_history(
    customer_id: str,
    question: str,
    history: List[dict],
    n_results: int = 5,
    model: str = DEFAULT_MODEL,
) -> RAGResponse:
    try:
        return _run_rag(
            customer_id=customer_id,
            question=question,
            n_results=n_results,
            model=model,
            filters=None,
            history=history,
        )
    except Exception as exc:
        logger.error(
            "Unexpected failure in ask_with_history() for customer '%s' question '%s': %s",
            customer_id,
            question,
            exc,
            exc_info=True,
        )
        return _error_response(
            customer_id=customer_id,
            question=question,
            model=model,
            answer="An unexpected error occurred while processing your question.",
        )


def _run_rag(
    *,
    customer_id: str,
    question: str,
    n_results: int,
    model: str,
    filters: dict | None,
    history: List[dict] | None,
) -> RAGResponse:
    normalized_customer_id = str(customer_id or "").strip()
    normalized_question = str(question or "").strip()
    if not normalized_customer_id:
        return _error_response(
            customer_id=customer_id,
            question=question,
            model=model,
            answer="A customer ID is required to search the document collection.",
        )
    if not normalized_question:
        return _error_response(
            customer_id=normalized_customer_id,
            question=question,
            model=model,
            answer="A question is required to search your documents.",
        )

    logger.info(
        "RAG request customer='%s' question_length=%d model='%s'",
        normalized_customer_id,
        len(normalized_question),
        model,
    )

    query_results = query_collection(
        normalized_customer_id,
        normalized_question,
        n_results=n_results,
        filters=filters,
    )
    if not query_results:
        logger.warning(
            "No query results found for customer '%s' question_length=%d.",
            normalized_customer_id,
            len(normalized_question),
        )
        return _empty_result_response(
            customer_id=normalized_customer_id,
            question=normalized_question,
            model=model,
            answer="No relevant information found in your documents for this question.",
        )

    prioritized_results = _prioritize_by_recency(query_results)
    sources = _build_source_references(prioritized_results)
    conflict = _detect_conflicts(prioritized_results)
    system_prompt, user_prompt = _build_prompt(normalized_question, prioritized_results, conflict)

    try:
        answer = _call_groq(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            history=history,
            model=model,
        )
    except Exception as exc:
        logger.error(
            "Groq API failure for customer '%s' question '%s': %s",
            normalized_customer_id,
            normalized_question,
            exc,
        )
        return _error_response(
            customer_id=normalized_customer_id,
            question=normalized_question,
            model=model,
            answer="I couldn't generate an answer because the language model service is unavailable or not configured correctly.",
            sources=sources,
            conflict=conflict,
        )

    sources_display = _format_sources_for_display(sources, conflict)
    logger.info(
        "RAG response customer='%s' chunks=%d model='%s' conflict_detected=%s",
        normalized_customer_id,
        len(prioritized_results),
        model,
        conflict.detected,
    )
    return RAGResponse(
        answer=answer,
        sources=sources,
        conflict=conflict,
        model_used=model,
        chunks_used=len(prioritized_results),
        customer_id=normalized_customer_id,
        question=normalized_question,
        sources_display=sources_display,
    )


def _build_prompt(
    question: str,
    query_results: List[QueryResult],
    conflict: ConflictInfo,
) -> tuple[str, str]:
    system_prompt = (
        "You are a retrieval assistant for SME business knowledge. "
        "Answer using only the provided context. "
        "Never make up information not present in the context. "
        "If the answer is not in the context, say \"I don't have enough information in your documents to answer this\". "
        "Always cite sources using the [DOC-N] labels provided. "
        "Be concise and factual. "
        "When multiple sources are provided, treat the most recently dated source as the authoritative one. "
        "Email communications represent the latest updates from customers or colleagues and should be trusted over older policy documents or spreadsheets when they contain conflicting information. "
        "Always mention the date of the source you are relying on in your answer. "
        "When a CONFLICT DETECTED section is present in the context: "
        "You must explicitly acknowledge the contradiction in your answer. "
        "You must state which source you are relying on and why. "
        "You must quote or closely reference the specific text from the trusted source that supports your answer, citing it as [TRUST-N]. "
        "You must also reference the conflicting source as [CONFLICT-N] and explain what it says differently so the user understands both sides. "
        "Never silently pick one source without explaining the conflict to the user. "
        "End your answer with a conflict summary in this format: "
        "Conflict summary: {trusted_file} (dated {trusted_date}) states [summary of trusted claim]. "
        "{conflicting_file} (dated {conflicting_date}) states [summary of conflicting claim]. "
        "Relying on {trusted_file} as it is more recent."
    )

    context_blocks: list[str] = []
    for index, result in enumerate(query_results, start=1):
        metadata = result.metadata or {}
        context_blocks.append(
            "\n".join(
                [
                    f"[DOC-{index}]",
                    f"Source: {metadata.get('source_file', '')}",
                    f"Page: {metadata.get('page', '')}",
                    f"Date: {_display_date(metadata)}",
                    f"Type: {metadata.get('block_type', '')}",
                    f"Section: {metadata.get('heading_context', '')}",
                    "---",
                    result.text,
                ]
            )
        )

    user_parts = [
        "Context:",
        "\n\n".join(context_blocks),
    ]
    if conflict.detected:
        user_parts.append(_build_conflict_evidence_block(query_results, conflict))
    user_parts.append(f"Question: {question}")
    user_prompt = "\n\n".join(part for part in user_parts if part.strip())

    logger.debug("System prompt sent to Groq:\n%s", system_prompt)
    logger.debug("User prompt sent to Groq:\n%s", user_prompt)
    return system_prompt, user_prompt


def _call_groq(
    system_prompt: str,
    user_prompt: str,
    history: List[dict] | None,
    model: str,
) -> str:
    if _groq_client is None:
        raise RuntimeError("Groq client is unavailable. Install groq and set GROQ_API_KEY.")
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set.")

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        history_slice = history[-6:]
        if len(history) > 6:
            logger.warning("Conversation history truncated from %d to 6 turns.", len(history))
        for entry in history_slice:
            role = str(entry.get("role", "")).strip()
            content = str(entry.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})

    completion = _groq_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    response_text = completion.choices[0].message.content if completion.choices else ""
    return str(response_text or "").strip()


def _detect_conflicts(query_results: List[QueryResult]) -> ConflictInfo:
    grouped = _group_results_by_source(query_results)
    logger.debug("Conflict detection evaluating %d source files.", len(grouped))
    if len(grouped) <= 1:
        return _empty_conflict()

    grouped_items: list[dict[str, Any]] = []
    for source_file, results in grouped.items():
        resolved_datetime, resolved_date = _resolve_result_datetime(results[0])
        source_type = str(results[0].metadata.get("source_type", "") or "")
        grouped_items.append(
            {
                "source_file": source_file,
                "results": results,
                "resolved_datetime": resolved_datetime,
                "resolved_date": resolved_date,
                "source_type": source_type,
            }
        )

    unique_dates = {item["resolved_datetime"] for item in grouped_items}
    if len(unique_dates) <= 1:
        logger.debug("Multiple sources retrieved but no date-based conflict was detected.")
        return _empty_conflict()

    grouped_items.sort(key=lambda item: item["resolved_datetime"], reverse=True)
    trusted_item = grouped_items[0]
    conflicting_items = grouped_items[1:]
    conflicting_item = conflicting_items[0]

    trusted_file = str(trusted_item["source_file"])
    trusted_date = str(trusted_item["resolved_date"])
    conflicting_file = str(conflicting_item["source_file"])
    conflicting_date = str(conflicting_item["resolved_date"])

    email_priority_applied = (
        trusted_item["source_type"] == "email"
        and conflicting_item["source_type"] in {"pdf", "spreadsheet"}
        and trusted_item["resolved_datetime"] > conflicting_item["resolved_datetime"]
    )
    if email_priority_applied:
        logger.info(
            "Email priority rule applied: trusting '%s' over '%s'.",
            trusted_file,
            conflicting_file,
        )

    explanation = (
        f"Conflict detected - {conflicting_file} (dated {conflicting_date}) and "
        f"{trusted_file} (dated {trusted_date}) contain potentially different information. "
        f"Trusting {trusted_file} as it is more recent."
    )
    if email_priority_applied:
        explanation += " The more recent email communication overrides the older static document."

    trusted_references = _build_source_references(trusted_item["results"])
    conflicting_references = _build_source_references(conflicting_item["results"])
    logger.debug(
        "Conflict detected. trusted_file='%s' conflicting_file='%s' trusted_date='%s' conflicting_date='%s'",
        trusted_file,
        conflicting_file,
        trusted_date,
        conflicting_date,
    )
    return ConflictInfo(
        detected=True,
        conflicting_files=[str(item["source_file"]) for item in conflicting_items],
        trusted_file=trusted_file,
        trusted_date=trusted_date,
        explanation=explanation,
        trusted_references=trusted_references,
        conflicting_references=conflicting_references,
    )


def _prioritize_by_recency(query_results: List[QueryResult]) -> List[QueryResult]:
    if not query_results:
        return []

    grouped = _group_results_by_source(query_results)
    grouped_items: list[dict[str, Any]] = []
    for source_file, results in grouped.items():
        resolved_datetime, resolved_date = _resolve_result_datetime(results[0])
        source_type = str(results[0].metadata.get("source_type", "") or "")
        grouped_items.append(
            {
                "source_file": source_file,
                "results": results,
                "resolved_datetime": resolved_datetime,
                "resolved_date": resolved_date,
                "source_type": source_type,
            }
        )

    most_recent_datetime = max(
        (item["resolved_datetime"] for item in grouped_items),
        default=_OLDEST_POSSIBLE_DATE,
    )
    for item in grouped_items:
        item["email_boost"] = (
            item["source_type"] == "email"
            and item["resolved_datetime"] != _OLDEST_POSSIBLE_DATE
            and most_recent_datetime - item["resolved_datetime"] <= timedelta(days=90)
        )

    grouped_items.sort(
        key=lambda item: (item["email_boost"], item["resolved_datetime"]),
        reverse=True,
    )
    logger.debug(
        "Prioritized source ordering: %s",
        [
            f"{item['source_file']} ({item['resolved_date'] or 'unknown'})"
            for item in grouped_items
        ],
    )

    ordered_results: list[QueryResult] = []
    for item in grouped_items:
        ordered_results.extend(item["results"])
    return ordered_results


def _build_source_references(query_results: List[QueryResult]) -> List[SourceReference]:
    sources: list[SourceReference] = []
    for result in query_results:
        metadata = result.metadata or {}
        source = SourceReference(
            source_file=str(metadata.get("source_file", "")),
            page=metadata.get("page", ""),
            block_type=str(metadata.get("block_type", "")),
            heading_context=str(metadata.get("heading_context", "")),
            document_date=str(metadata.get("document_date", "")),
            chunk_id=str(result.chunk_id),
            distance=float(result.distance),
            uploaded_at=str(metadata.get("uploaded_at", "")),
            text_excerpt=_snippet(result.text),
        )
        logger.debug("Built source reference: %s", source)
        sources.append(source)
    return sources


def _format_sources_for_display(
    sources: List[SourceReference],
    conflict: ConflictInfo | None = None,
) -> str:
    lines = ["Sources:"]
    if not sources:
        lines.append("  (none)")
    else:
        for index, source in enumerate(sources, start=1):
            location = _source_location_label(source)
            section = source.heading_context or source.block_type or "chunk"
            lines.append(
                f"  [{index}] {source.source_file} - {location} - {section} ({_source_display_date(source)})"
            )

    if conflict and conflict.detected:
        trusted_reference = conflict.trusted_references[0] if conflict.trusted_references else None
        conflicting_reference = (
            conflict.conflicting_references[0] if conflict.conflicting_references else None
        )
        lines.append("")
        lines.append("Conflict References:")
        if trusted_reference is not None:
            lines.append(
                "  Trusted:    "
                f"{trusted_reference.source_file} - {_source_location_label(trusted_reference)} - "
                f"\"{trusted_reference.text_excerpt}\" ({_source_display_date(trusted_reference)})"
            )
        if conflicting_reference is not None:
            lines.append(
                "  Overridden: "
                f"{conflicting_reference.source_file} - {_source_location_label(conflicting_reference)} - "
                f"\"{conflicting_reference.text_excerpt}\" ({_source_display_date(conflicting_reference)})"
            )
        decision_suffix = _decision_recency_suffix(conflict)
        lines.append(
            f"  Decision:   Trusting {conflict.trusted_file}{decision_suffix}"
        )

    return "\n".join(lines)


def _group_results_by_source(query_results: List[QueryResult]) -> dict[str, List[QueryResult]]:
    grouped: dict[str, List[QueryResult]] = {}
    for result in query_results:
        metadata = result.metadata or {}
        source_file = str(metadata.get("source_file", "") or "unknown")
        grouped.setdefault(source_file, []).append(result)
    return grouped


def _resolve_result_datetime(result: QueryResult) -> tuple[datetime, str]:
    metadata = result.metadata or {}
    document_date = str(metadata.get("document_date", "") or "").strip()
    parsed_document_date = _parse_date_value(document_date)
    if parsed_document_date is not None:
        return parsed_document_date, document_date

    uploaded_at = str(metadata.get("uploaded_at", "") or "").strip()
    parsed_uploaded_at = _parse_date_value(uploaded_at)
    if parsed_uploaded_at is not None:
        return parsed_uploaded_at, uploaded_at

    return _OLDEST_POSSIBLE_DATE, ""


def _parse_date_value(value: str) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None

    iso_candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        return _coerce_to_utc(parsed)

    for fmt in _DATE_FORMATS:
        try:
            return _coerce_to_utc(datetime.strptime(normalized, fmt))
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is not None:
        return _coerce_to_utc(parsed)

    logger.warning("Could not parse document date '%s'. Treating it as oldest.", normalized)
    return None


def _coerce_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _display_date(metadata: dict[str, Any]) -> str:
    document_date = str(metadata.get("document_date", "") or "").strip()
    if document_date:
        return document_date
    return str(metadata.get("uploaded_at", "") or "").strip()


def _source_display_date(source: SourceReference) -> str:
    return source.document_date or source.uploaded_at or ""


def _source_location_label(source: SourceReference) -> str:
    page = source.page
    if page not in {"", None}:
        return f"Page {page}"
    block_type = source.block_type.replace("_", " ").strip()
    if not block_type:
        return "Chunk"
    return block_type.title()


def _build_conflict_evidence_block(
    query_results: List[QueryResult],
    conflict: ConflictInfo,
) -> str:
    trusted_lookup = {reference.chunk_id for reference in conflict.trusted_references[:2]}
    conflicting_lookup = {reference.chunk_id for reference in conflict.conflicting_references[:2]}
    trusted_results = [result for result in query_results if result.chunk_id in trusted_lookup][:2]
    conflicting_results = [result for result in query_results if result.chunk_id in conflicting_lookup][:2]

    conflicting_file = (
        conflict.conflicting_references[0].source_file if conflict.conflicting_references else ""
    )
    conflicting_date = (
        _source_display_date(conflict.conflicting_references[0])
        if conflict.conflicting_references
        else ""
    )

    lines = [
        "CONFLICT DETECTED",
        "-----------------",
        "Two or more sources contain contradictory information on this topic.",
        "",
        f"TRUSTED SOURCE: {conflict.trusted_file} (dated {conflict.trusted_date})",
    ]
    for index, result in enumerate(trusted_results, start=1):
        metadata = result.metadata or {}
        lines.extend(
            [
                f"  [TRUST-{index}]",
                f"  Source: {metadata.get('source_file', '')}",
                f"  Page: {metadata.get('page', '')}",
                f"  Date: {_display_date(metadata)}",
                f"  Section: {metadata.get('heading_context', '')}",
                "  ---",
                f"  {result.text}",
            ]
        )

    lines.extend(
        [
            "",
            f"OVERRIDDEN SOURCE: {conflicting_file} (dated {conflicting_date})",
        ]
    )
    for index, result in enumerate(conflicting_results, start=1):
        metadata = result.metadata or {}
        lines.extend(
            [
                f"  [CONFLICT-{index}]",
                f"  Source: {metadata.get('source_file', '')}",
                f"  Page: {metadata.get('page', '')}",
                f"  Date: {_display_date(metadata)}",
                f"  Section: {metadata.get('heading_context', '')}",
                "  ---",
                f"  {result.text}",
            ]
        )

    lines.extend(
        [
            "",
            f"Reason for trusting {conflict.trusted_file}: More recent date. {conflict.explanation}",
            "-----------------",
        ]
    )
    return "\n".join(lines)


def _snippet(text: str, limit: int = 80) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _decision_recency_suffix(conflict: ConflictInfo) -> str:
    if not conflict.detected or not conflict.conflicting_references:
        return "."

    conflicting_date = _source_display_date(conflict.conflicting_references[0])
    trusted_datetime = _parse_date_value(conflict.trusted_date)
    conflicting_datetime = _parse_date_value(conflicting_date)
    if trusted_datetime is None or conflicting_datetime is None:
        return " - more recent."

    delta_days = abs((trusted_datetime - conflicting_datetime).days)
    months = max(1, delta_days // 30) if delta_days else 0
    if months:
        return f" - more recent by {months} month{'s' if months != 1 else ''}."
    return " - more recent."


def _empty_conflict() -> ConflictInfo:
    return ConflictInfo(
        detected=False,
        conflicting_files=[],
        trusted_file="",
        trusted_date="",
        explanation="",
        trusted_references=[],
        conflicting_references=[],
    )


def _error_response(
    *,
    customer_id: str,
    question: str,
    model: str,
    answer: str,
    sources: List[SourceReference] | None = None,
    conflict: ConflictInfo | None = None,
) -> RAGResponse:
    response_sources = sources or []
    response_conflict = conflict or _empty_conflict()
    return RAGResponse(
        answer=answer,
        sources=response_sources,
        conflict=response_conflict,
        model_used=model,
        chunks_used=len(response_sources),
        customer_id=str(customer_id or ""),
        question=str(question or ""),
        sources_display=_format_sources_for_display(response_sources, response_conflict),
    )


def _empty_result_response(
    *,
    customer_id: str,
    question: str,
    model: str,
    answer: str,
) -> RAGResponse:
    return _error_response(
        customer_id=customer_id,
        question=question,
        model=model,
        answer=answer,
        sources=[],
        conflict=_empty_conflict(),
    )


if __name__ == "__main__":
    response = ask(
        customer_id="demo-customer",
        question="What is the refund policy for bulk orders?",
    )

    print("ANSWER:", response.answer)
    print()
    print(response.sources_display)
    if response.conflict.detected:
        print()
        print("CONFLICT DETECTED")
        print("Trusted file:     ", response.conflict.trusted_file)
        print("Trusted date:     ", response.conflict.trusted_date)
        print("Explanation:      ", response.conflict.explanation)
        print("Trusted chunks:   ", len(response.conflict.trusted_references))
        print("Conflicting chunks:", len(response.conflict.conflicting_references))
