"""Sync articles from Postgres into a Pinecone vector index.

Usage (from repo root):

    python -m embeddings.pg_to_pinecone_sync

Before running, ensure:
  - Postgres is reachable via ``db.postgres_client.get_conn``.
  - ``PINECONE_API_KEY`` is set in your environment.
  - You have ``pinecone`` installed: ``pip install pinecone-client`` (or the
    latest Pinecone SDK as per their docs).

This script:
  1. Reads rows from the ``news_articles`` table.
  2. Chunks each article's Hindi content using ``preprocessing.chunking``.
  3. Embeds chunks with ``embeddings.embedder.embed_texts``.
  4. Upserts chunk vectors + metadata into Pinecone via ``vector_db.client``.
"""
from __future__ import annotations
    
from typing import Any, Dict, List
from pathlib import Path
import sys

# Ensure project root is on sys.path so that the local "db", "preprocessing",
# "embeddings", and "vector_db" packages are imported instead of similarly
# named third-party packages when this file is executed as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.postgres_client import get_conn
from preprocessing.chunking import chunk_document
from embeddings.embedder import embed_texts
from vector_db.client import from_config as vector_client_from_config


def _sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure metadata only contains types allowed by Pinecone.

    Pinecone requires values to be string, number, boolean, or list of strings.
    ``None`` values are dropped.
    """
    clean: Dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            # Drop nulls entirely.
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, (list, tuple)):
            # Keep lists as lists of strings.
            clean[key] = [str(v) for v in value]
        else:
            # Fallback: convert complex types (dicts, etc.) to string.
            clean[key] = str(value)
    return clean


def fetch_articles(limit: int | None = None) -> List[Dict[str, Any]]:
    """Fetch articles from the ``news_articles`` table.

    Returns list of dicts with at least: id, site, category, url, title,
    content_hi, scraped_at, meta.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            base_query = (
                "SELECT id, site, category, url, title, lang, content_hi, "
                "scraped_at, meta FROM news_articles"
            )
            params = []
            if limit is not None:
                base_query += " LIMIT %s"
                params.append(limit)

            cur.execute(base_query, params)
            rows = cur.fetchall()

        columns = [
            "id",
            "site",
            "category",
            "url",
            "title",
            "lang",
            "content_hi",
            "scraped_at",
            "meta",
        ]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


def sync_pg_to_pinecone(config: Dict[str, Any]) -> None:
    """Main sync routine.

    ``config`` keys:
      - limit: Optional[int] to cap number of articles.
      - vector_db: dict passed straight to ``vector_db.client.from_config``.
    """
    limit: int | None = config.get("limit")
    vdb_config: Dict[str, Any] = config.get("vector_db", {})

    vdb = vector_client_from_config(vdb_config)

    articles = fetch_articles(limit=limit)
    if not articles:
        print("[sync_pg_to_pinecone] No articles found in news_articles table.")
        return

    print(f"[sync_pg_to_pinecone] Syncing {len(articles)} articles to Pinecone (limit={limit})...")

    for idx, article in enumerate(articles, start=1):
        article_id = str(article["id"])
        base_meta = {
            "article_id": article_id,
            "site": article["site"],
            "category": article["category"],
            "url": article["url"],
            "title": article["title"],
            # Default to "hi" if lang is null/empty so Pinecone doesn't see a null.
            "lang": article.get("lang") or "hi",
        }

        # Build a doc compatible with ``chunk_document``.
        doc = {
            "id": f"news:{article_id}",
            "text": article["content_hi"],
            "meta": article.get("meta") or {},
        }

        chunks = chunk_document(doc)
        if not chunks:
            print(f"[sync_pg_to_pinecone] Article {article_id} produced 0 chunks; skipping.")
            continue

        texts = [c["text"] for c in chunks]
        vectors = embed_texts(texts)

        ids: List[str] = [c["id"] for c in chunks]
        metadatas: List[Dict[str, Any]] = []

        for chunk, vector in zip(chunks, vectors):  # vector unused but sanity-zip
            chunk_meta = dict(base_meta)
            # Merge in any per-chunk metadata from the chunker (e.g., chunk_index).
            chunk_meta.update(chunk.get("meta", {}))
            metadatas.append(_sanitize_metadata(chunk_meta))

        try:
            print(
                f"[sync_pg_to_pinecone] Upserting article {article_id} "
                f"({idx}/{len(articles)}), chunks={len(chunks)}, vectors={len(vectors)}"
            )
            vdb.upsert(ids, vectors, metadatas)
        except Exception as e:  # pragma: no cover - diagnostic logging
            print(f"[sync_pg_to_pinecone] ERROR upserting article {article_id}: {e}")
            # continue with the next article instead of aborting the whole sync
            continue

    print("[sync_pg_to_pinecone] Done.")


def run(config: Dict[str, Any]) -> None:
    sync_pg_to_pinecone(config)


if __name__ == "__main__":
    # Minimal default config; override as needed or import ``run`` from Python.
    default_config: Dict[str, Any] = {
        # Limit can be set to a small number while testing.
        "limit": None,
        "vector_db": {
            # index_name can be changed; dimension must match your embedder output size.
            "index_name": "news-embeddings",
            "dimension": 1,  # current dummy embedder returns 1-D vectors
            # metric / cloud / region can be customized as needed.
            "metric": "cosine",
            "cloud": "aws",
            "region": "us-east-1",
        },
    }

    run(default_config)
