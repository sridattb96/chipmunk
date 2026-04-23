"""ChromaDB vector store. Separate from SQLite db - stores embeddings with metadata."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

import chromadb

from app.config import CHROMA_PATH, CHROMA_HTTP_URL

COLLECTION_NAME = "chipmunk_vectors"

EntityType = Literal["summary", "topic", "decision", "combined"]

_client = None


def _get_client():
    """Return ChromaDB client: HttpClient when CHROMA_HTTP_URL is set, else PersistentClient."""
    global _client
    if _client is not None:
        return _client
    if CHROMA_HTTP_URL:
        parsed = urlparse(CHROMA_HTTP_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8000)
        ssl = parsed.scheme == "https"
        _client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
    else:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def get_collection():
    """Get or create the chipmunk vectors collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Vector embeddings for summaries, topics, and decisions"},
    )


def add_record(
    id: str,
    vector: list[float],
    metadata: dict,
) -> None:
    """
    Add a vector record to ChromaDB.

    metadata must include:
        entity_type: "summary" | "topic" | "decision"
        call_id: str (UUID)
        org_id: str (UUID)
        created_at: str (ISO timestamp)
        topic_id: str | None (optional, use "" when null)
        canonical_topic_id: str | None (optional, use "" when null)

    ChromaDB metadata values must be str, int, float, or bool.
    """
    # Normalize metadata for ChromaDB (no None, no nested dicts)
    safe = {
        "entity_type": str(metadata.get("entity_type", "")),
        "call_id": str(metadata.get("call_id", "")),
        "topic_id": str(metadata.get("topic_id") or ""),
        "canonical_topic_id": str(metadata.get("canonical_topic_id") or ""),
        "org_id": str(metadata.get("org_id", "")),
        "created_at": str(metadata.get("created_at", datetime.utcnow().isoformat())),
    }
    coll = get_collection()
    coll.add(ids=[id], embeddings=[vector], metadatas=[safe])


def add_records(
    ids: list[str],
    vectors: list[list[float]],
    metadatas: list[dict],
) -> None:
    """
    Add multiple vector records in one batch.

    Each metadata dict must include entity_type, call_id, org_id.
    topic_id and canonical_topic_id are optional (use "" when null).
    """
    safe_list = []
    for m in metadatas:
        safe_list.append({
            "entity_type": str(m.get("entity_type", "")),
            "call_id": str(m.get("call_id", "")),
            "topic_id": str(m.get("topic_id") or ""),
            "canonical_topic_id": str(m.get("canonical_topic_id") or ""),
            "org_id": str(m.get("org_id", "")),
            "created_at": str(m.get("created_at", datetime.utcnow().isoformat())),
        })
    coll = get_collection()
    coll.add(ids=ids, embeddings=vectors, metadatas=safe_list)


def query(
    query_embeddings: list[list[float]],
    n_results: int = 10,
    where: dict | None = None,
) -> dict:
    """
    Query the collection by vector similarity.

    where: optional metadata filter, e.g. {"entity_type": "topic", "org_id": "..."}
    Returns ChromaDB query result with ids, distances, metadatas.
    """
    coll = get_collection()
    return coll.query(
        query_embeddings=query_embeddings,
        n_results=n_results,
        where=where,
    )
