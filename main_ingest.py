#!/usr/bin/env python3
"""Main ingestion + vector sync pipeline.

Run from the repo root, for example:

    python main_ingest.py

This will:
  1. Ingest Aaj Tak articles into Postgres (and write processed JSON).
  2. Ingest The Hindu articles into Postgres and Pinecone directly.
  3. Optionally run a Postgres→Pinecone backfill/sync job.

All three stages assume the crawlers have already populated their
respective raw/metadata directories.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv


# Resolve project root and load environment variables from .env before
# importing any modules that rely on DATABASE_URL / PINECONE_*.
ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT / ".env")

# Ensure project root is on sys.path so that local packages are importable
# when this file is executed as a script.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion import aaj_tak_ingest, hindu_ingest
from embeddings import pg_to_pinecone_sync


# Shared default configuration for the Pinecone-backed vector DB.
# Values are taken from environment variables with sensible defaults,
# and the API key itself is read inside vector_db.client from PINECONE_API_KEY.
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "news-embeddings")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")

# Dimension must match ``embeddings.embedder.embed_texts`` output size.
VECTOR_DB_CONFIG: Dict[str, Any] = {
    "index_name": PINECONE_INDEX_NAME,
    "dimension": 1,  # current dummy embedder returns 1-D vectors
    "metric": "cosine",
    "cloud": PINECONE_CLOUD,
    "region": PINECONE_ENVIRONMENT,
}


def run_ingestion_pipeline(run_pg_sync: bool = True) -> None:
    """Run the full ingestion + (optional) PG→Pinecone sync pipeline."""
    print("[main_ingest] Starting Aaj Tak ingestion → Postgres...")
    # Aaj Tak: writes processed JSON and upserts to Postgres.
    aaj_tak_ingest.run({})

    print("[main_ingest] Starting The Hindu ingestion → Postgres + Pinecone...")
    hindu_ingest.run(
        {
            "raw_root": hindu_ingest.DEFAULT_RAW_ROOT,
            "meta_root": hindu_ingest.DEFAULT_META_ROOT,
            "output_root": hindu_ingest.DEFAULT_OUTPUT_ROOT,
            "store_in_db": True,
            "push_to_vector_db": True,
            "vector_db": VECTOR_DB_CONFIG,
        }
    )

    if run_pg_sync:
        print("[main_ingest] Starting Postgres → Pinecone sync...")
        pg_to_pinecone_sync.run(
            {
                "limit": None,  # set a small int while testing, if desired
                "vector_db": VECTOR_DB_CONFIG,
            }
        )

    print("[main_ingest] Ingestion pipeline complete.")


def main() -> None:
    # For now we always run the PG→Pinecone sync after ingestion.
    run_ingestion_pipeline(run_pg_sync=True)


if __name__ == "__main__":
    main()
