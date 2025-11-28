"""Ingestion + Postgres + vector DB pipeline for The Hindu articles.

This script expects the RSS-based crawler (the Hindu crawler module) to have written:
  - markdown under   hindu_pages_by_section/<section>/<slug>.md
  - metadata under   hindu_meta_by_section/<section>/<slug>.json

It then:
  1. Converts them into structured document dictionaries.
  2. Writes JSON docs under data/processed/hindu/<section>/<slug>.json.
  3. Upserts each article into the PostgreSQL `news_articles` table.
  4. Immediately chunks + embeds each article and upserts vectors
     into a Pinecone-backed vector index via `vector_db.client`.

Run from the repo root, e.g.:

    python ingestion/hindu_ingest.py

Configurable behaviour is exposed via the `run(config)` function.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
import sys

# Ensure project root is on sys.path so that "preprocessing", "db", and
# "vector_db" can be imported when executed as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from preprocessing.cleaners import basic_clean
from preprocessing.chunking import chunk_document
from embeddings.embedder import embed_texts
from db.postgres_client import upsert_article
from vector_db.client import from_config as vector_client_from_config


DEFAULT_RAW_ROOT = "hindu_pages_by_section"
DEFAULT_META_ROOT = "hindu_meta_by_section"
DEFAULT_OUTPUT_ROOT = "data/processed/hindu"


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


def iter_docs(
    raw_root: str = DEFAULT_RAW_ROOT,
    meta_root: str = DEFAULT_META_ROOT,
) -> Iterable[Dict[str, Any]]:
    """Yield structured docs from Hindu markdown + metadata.

    The crawler writes:
      - markdown under hindu_pages_by_section/<section>/<slug>.md
      - metadata under hindu_meta_by_section/<section>/<slug>.json

    Sections map roughly to the FEEDS keys in the crawler, e.g. "india", "world".
    """
    raw_base = Path(raw_root)
    meta_base = Path(meta_root)

    for md_path in raw_base.rglob("*.md"):
        section = md_path.parent.name
        stem = md_path.stem

        meta_path = meta_base / section / f"{stem}.json"

        text = md_path.read_text(encoding="utf-8")
        # Light normalization; content is mostly English, but this keeps
        # whitespace tidy without touching substantive characters.
        text = basic_clean(text)

        meta: Dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        site = meta.get("site", "the_hindu")
        url = meta.get("url")
        title = meta.get("title")
        lang = meta.get("lang") or "en"
        ts = meta.get("timestamp")  # ISO 8601 string from crawler (if any)

        scraped_at = ts or datetime.utcnow().isoformat() + "Z"

        doc: Dict[str, Any] = {
            "id": f"{site}/{section}/{stem}",
            "site": site,
            "category": section,
            "url": url,
            "title": title,
            "lang": lang,
            "text": text,
            "meta": meta,
            "scraped_at": scraped_at,
        }
        yield doc


def _upsert_vectors_for_doc(doc: Dict[str, Any], vdb_config: Dict[str, Any]) -> None:
    """Chunk + embed a single doc and upsert into the vector DB.

    `vdb_config` is passed directly to `vector_db.client.from_config`.
    """
    vdb = vector_client_from_config(vdb_config)

    base_meta = {
        "article_id": doc["id"],
        "site": doc["site"],
        "category": doc["category"],
        "url": doc["url"],
        "title": doc["title"],
        "lang": doc.get("lang") or "en",
    }

    chunks = chunk_document({"id": doc["id"], "text": doc["text"], "meta": doc.get("meta") or {}})
    if not chunks:
        return

    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)

    ids: List[str] = [c["id"] for c in chunks]
    metadatas: List[Dict[str, Any]] = []

    for chunk, _vector in zip(chunks, vectors):  # vector unused but sanity-zip
        chunk_meta = dict(base_meta)
        chunk_meta.update(chunk.get("meta", {}))
        metadatas.append(_sanitize_metadata(chunk_meta))

    vdb.upsert(ids, vectors, metadatas)


def run(config: Dict[str, Any]) -> None:
    """Ingestion entrypoint for The Hindu docs.

    Config keys (all optional):
      - raw_root: str (default DEFAULT_RAW_ROOT)
      - meta_root: str (default DEFAULT_META_ROOT)
      - output_root: str (default DEFAULT_OUTPUT_ROOT)
      - store_in_db: bool (default True)
      - push_to_vector_db: bool (default True)
      - vector_db: dict passed straight to `vector_db.client.from_config`
    """
    raw_root = config.get("raw_root", DEFAULT_RAW_ROOT)
    meta_root = config.get("meta_root", DEFAULT_META_ROOT)
    output_root = config.get("output_root", DEFAULT_OUTPUT_ROOT)
    store_in_db: bool = config.get("store_in_db", True)
    push_to_vector_db: bool = config.get("push_to_vector_db", True)
    vdb_config: Dict[str, Any] = config.get("vector_db", {})

    out_base = Path(output_root)
    out_base.mkdir(parents=True, exist_ok=True)

    for doc in iter_docs(raw_root=raw_root, meta_root=meta_root):
        section = doc["category"]
        stem = doc["id"].split("/")[-1]

        out_dir = out_base / section
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{stem}.json"
        out_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if store_in_db:
            upsert_article(doc)

        if push_to_vector_db:
            _upsert_vectors_for_doc(doc, vdb_config)


if __name__ == "__main__":
    # Minimal default config; override as needed or import `run` from Python.
    default_config: Dict[str, Any] = {
        "raw_root": DEFAULT_RAW_ROOT,
        "meta_root": DEFAULT_META_ROOT,
        "output_root": DEFAULT_OUTPUT_ROOT,
        "store_in_db": True,
        "push_to_vector_db": True,
        "vector_db": {
            # Should match the index used elsewhere (e.g., pg_to_pinecone_sync).
            "index_name": "news-embeddings",
            # Dimension must match your embedder output size.
            "dimension": 1,  # current dummy embedder returns 1-D vectors
            "metric": "cosine",
            "cloud": "aws",
            "region": "us-east-1",
        },
    }

    run(default_config)
