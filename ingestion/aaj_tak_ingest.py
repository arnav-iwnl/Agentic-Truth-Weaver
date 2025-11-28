"""Ingestion script for Aaj Tak content.

Reads markdown + metadata produced by the Aaj Tak crawler and:
  - converts them into structured document dictionaries;
  - writes JSON docs under data/processed/aaj_tak/<category>/;
  - upserts each article into the PostgreSQL `news_articles` table.

Run from the repo root, e.g.:

    python ingestion/aaj_tak_ingest.py

Make sure you have:
  - run the Aaj Tak crawler first (so data/raw/aaj_tak and data/raw_meta/aaj_tak exist),
  - installed psycopg2-binary,
  - created the `news_articles` table and set PG* env vars.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from preprocessing.cleaners import basic_clean
from db.postgres_client import upsert_article


def iter_docs(
    raw_root: str = "data/raw/aaj_tak",
    meta_root: str = "data/raw_meta/aaj_tak",
) -> Iterable[Dict[str, Any]]:
    """Yield structured docs from Aaj Tak markdown + metadata.

    The crawler writes:
      - markdown under data/raw/aaj_tak/<category>/<slug>.md
      - metadata under data/raw_meta/aaj_tak/<category>/<slug>.json
    """
    raw_base = Path(raw_root)
    meta_base = Path(meta_root)

    for md_path in raw_base.rglob("*.md"):
        category = md_path.parent.name
        stem = md_path.stem

        meta_path = meta_base / category / f"{stem}.json"

        text = md_path.read_text(encoding="utf-8")
        # Light normalization that preserves Devanagari script.
        text = basic_clean(text)

        meta: Dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        site = meta.get("site", "aaj_tak")
        url = meta.get("url")
        title = meta.get("title")
        lang = meta.get("lang") or "hi"
        ts = meta.get("timestamp")  # ISO 8601 string from crawler

        scraped_at = ts or datetime.utcnow().isoformat() + "Z"

        doc: Dict[str, Any] = {
            "id": f"{site}/{category}/{stem}",
            "site": site,
            "category": category,
            "url": url,
            "title": title,
            "lang": lang,
            "text": text,
            "meta": meta,
            "scraped_at": scraped_at,
        }
        yield doc


def run(config: Dict[str, Any]) -> None:
    """Ingestion entrypoint for Aaj Tak docs.

    Config keys (all optional):
      - raw_root: str (default "data/raw/aaj_tak")
      - meta_root: str (default "data/raw_meta/aaj_tak")
      - output_root: str (default "data/processed/aaj_tak")
      - store_in_db: bool (default True)
    """
    raw_root = config.get("raw_root", "data/raw/aaj_tak")
    meta_root = config.get("meta_root", "data/raw_meta/aaj_tak")
    output_root = config.get("output_root", "data/processed/aaj_tak")
    store_in_db = config.get("store_in_db", True)

    out_base = Path(output_root)
    out_base.mkdir(parents=True, exist_ok=True)

    for doc in iter_docs(raw_root=raw_root, meta_root=meta_root):
        category = doc["category"]
        stem = doc["id"].split("/")[-1]

        out_dir = out_base / category
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{stem}.json"
        out_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if store_in_db:
            upsert_article(doc)


if __name__ == "__main__":
    run({})
