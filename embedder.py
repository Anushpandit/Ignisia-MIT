from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List

import chromadb
from sentence_transformers import SentenceTransformer

from chunker import Chunk


logger = logging.getLogger("embedder")

_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
_chroma_client = chromadb.PersistentClient(path="./chroma_db")


@dataclass(slots=True)
class EmbedResult:
    total_chunks_received: int
    total_chunks_stored: int
    customers_processed: List[str]
    failed_customers: List[str]
    errors: List[str]


@dataclass(slots=True)
class QueryResult:
    text: str
    metadata: dict
    distance: float
    chunk_id: str


def _collection_name(customer_id: str) -> str:
    safe = customer_id.lower().strip().replace(" ", "_").replace("-", "_")
    return f"customer_{safe}"


def _make_chunk_id(chunk: Chunk, index: int) -> str:
    customer_id = chunk.metadata.get("customer_id", "unknown")
    source_file = chunk.metadata.get("source_file", "unknown")
    block_type = chunk.metadata.get("block_type", "unknown")
    page = chunk.metadata.get("page", "x")
    sub_index = chunk.metadata.get("sub_chunk_index", index)
    safe_file = source_file.replace("/", "_").replace(".", "_").replace(" ", "_")
    return f"{customer_id}__{safe_file}__{block_type}__p{page}__i{sub_index}"


def embed_and_store(chunks: List[Chunk]) -> EmbedResult:
    if not chunks:
        logger.warning("embed_and_store received an empty chunk list.")
        return EmbedResult(
            total_chunks_received=0,
            total_chunks_stored=0,
            customers_processed=[],
            failed_customers=[],
            errors=[],
        )

    grouped_chunks = group_chunks_by_customer(chunks)
    total_chunks_stored = 0
    customers_processed: list[str] = []
    failed_customers: list[str] = []
    errors: list[str] = []

    for customer_id, customer_chunks in grouped_chunks.items():
        result = _embed_customer_chunks(customer_id, customer_chunks)
        total_chunks_stored += result.total_chunks_stored
        customers_processed.extend(result.customers_processed)
        failed_customers.extend(result.failed_customers)
        errors.extend(result.errors)

    logger.info(
        "Processed embedding batch: received=%d stored=%d customers=%d failures=%s",
        len(chunks),
        total_chunks_stored,
        len(grouped_chunks),
        failed_customers,
    )
    return EmbedResult(
        total_chunks_received=len(chunks),
        total_chunks_stored=total_chunks_stored,
        customers_processed=customers_processed,
        failed_customers=failed_customers,
        errors=errors,
    )


def group_chunks_by_customer(chunks: List[Chunk]) -> dict[str, List[Chunk]]:
    grouped: dict[str, list[Chunk]] = {}

    for chunk in chunks:
        customer_id_value = chunk.metadata.get("customer_id", "")
        customer_id = str(customer_id_value).strip() if customer_id_value is not None else ""
        if not customer_id:
            customer_id = "unknown"
            logger.warning(
                "Chunk from source '%s' is missing customer_id; assigning to 'unknown'.",
                chunk.metadata.get("source_file", ""),
            )
        grouped.setdefault(customer_id, []).append(chunk)

    return grouped


def query_collection(
    customer_id: str,
    query_text: str,
    n_results: int = 5,
    filters: dict | None = None,
) -> List[QueryResult]:
    try:
        collection = _get_collection_if_exists(customer_id)
        if collection is None:
            logger.warning("Collection does not exist for customer '%s'.", customer_id)
            return []

        query_vector = _embedding_model.encode(
            [query_text],
            batch_size=64,
            show_progress_bar=False,
        ).tolist()[0]

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": n_results,
        }
        if filters is not None:
            query_kwargs["where"] = filters

        results = collection.query(**query_kwargs)
        logger.info(
            "Executed query for customer '%s' with %d results.",
            customer_id,
            len(results.get("ids", [[]])[0]) if results.get("ids") else 0,
        )
        return _build_query_results(results)
    except Exception as exc:
        logger.error("Failed query for customer '%s': %s", customer_id, exc)
        return []


def delete_customer_data(customer_id: str) -> bool:
    try:
        collection = _get_collection_if_exists(customer_id)
        if collection is None:
            logger.info("No collection found to delete for customer '%s'.", customer_id)
            return False

        _chroma_client.delete_collection(_collection_name(customer_id))
        logger.info("Deleted collection for customer '%s'.", customer_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete collection for customer '%s': %s", customer_id, exc)
        return False


def get_customer_stats(customer_id: str) -> dict:
    try:
        collection_name = _collection_name(customer_id)
        collection = _get_collection_if_exists(customer_id)
        if collection is None:
            return {
                "collection_name": collection_name,
                "chunk_count": 0,
                "customer_id": customer_id,
                "exists": False,
            }

        return {
            "collection_name": collection_name,
            "chunk_count": collection.count(),
            "customer_id": customer_id,
            "exists": True,
        }
    except Exception as exc:
        logger.error("Failed to get stats for customer '%s': %s", customer_id, exc)
        return {
            "collection_name": _collection_name(customer_id),
            "chunk_count": 0,
            "customer_id": customer_id,
            "exists": False,
        }


def _embed_customer_chunks(customer_id: str, chunks: List[Chunk]) -> EmbedResult:
    try:
        logger.info(
            "Embedding %d chunks for customer '%s'.",
            len(chunks),
            customer_id,
        )
        collection_name = _collection_name(customer_id)
        collection = _chroma_client.get_or_create_collection(collection_name)

        chunk_ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            chunk_id = _make_chunk_id(chunk, index)
            logger.debug("Generated chunk id '%s'.", chunk_id)
            chunk_ids.append(chunk_id)
            texts.append(chunk.text)
            metadatas.append(_sanitize_metadata(chunk.metadata))

        embeddings = _embedding_model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
        )
        logger.debug(
            "Embedding shape for customer '%s': (%d, %d)",
            customer_id,
            len(texts),
            len(embeddings.tolist()[0]) if texts else 0,
        )
        embedding_rows = embeddings.tolist()

        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=chunk_ids[start:end],
                embeddings=embedding_rows[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )
            logger.debug(
                "Upserted embedding batch for customer '%s': start=%d end=%d",
                customer_id,
                start,
                min(end, len(chunks)),
            )

        logger.info(
            "Stored %d chunks for customer '%s' in collection '%s'.",
            len(chunks),
            customer_id,
            collection_name,
        )
        return EmbedResult(
            total_chunks_received=len(chunks),
            total_chunks_stored=len(chunks),
            customers_processed=[customer_id],
            failed_customers=[],
            errors=[],
        )
    except Exception as exc:
        message = f"Customer '{customer_id}' embedding failed: {exc}"
        logger.error(message)
        return EmbedResult(
            total_chunks_received=len(chunks),
            total_chunks_stored=0,
            customers_processed=[],
            failed_customers=[customer_id],
            errors=[message],
        )


def _sanitize_metadata(metadata: dict) -> dict:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            sanitized[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


def _get_collection_if_exists(customer_id: str):
    collection_name = _collection_name(customer_id)
    try:
        return _chroma_client.get_collection(collection_name)
    except Exception:
        return None


def _build_query_results(results: dict[str, Any]) -> List[QueryResult]:
    ids = results.get("ids", [[]])
    documents = results.get("documents", [[]])
    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])

    query_results: list[QueryResult] = []
    first_ids = ids[0] if ids else []
    first_documents = documents[0] if documents else []
    first_metadatas = metadatas[0] if metadatas else []
    first_distances = distances[0] if distances else []

    for index, chunk_id in enumerate(first_ids):
        text = first_documents[index] if index < len(first_documents) else ""
        metadata = first_metadatas[index] if index < len(first_metadatas) else {}
        distance = float(first_distances[index]) if index < len(first_distances) else 0.0
        query_results.append(
            QueryResult(
                text=text,
                metadata=metadata,
                distance=distance,
                chunk_id=chunk_id,
            )
        )

    return query_results
