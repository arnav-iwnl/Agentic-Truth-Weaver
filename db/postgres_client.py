"""Minimal PostgreSQL client for the news_rag_orchestrator project.

Configuration is taken from environment variables (with sensible defaults):
  - PGHOST (default: "localhost")
  - PGPORT (default: "5432")
  - PGUSER (default: "postgres")
  - PGPASSWORD (default: "")
  - PGDATABASE (default: "news")

This module exposes `get_conn()` for obtaining a connection and `upsert_article()`
for inserting/updating Hindi news articles in the `news_articles` table.
"""
from __future__ import annotations
from dotenv import load_dotenv

import os
from typing import Any, Dict

import psycopg2
import psycopg2.extras

load_dotenv()


conn_str = os.getenv("DATABASE_URL")
def get_conn():
    """Create a new PostgreSQL connection using env vars.

    Callers are responsible for closing the connection.
    """
    if not conn_str:
      raise ValueError("DATABASE_URL environment variable is not set")

    # Return the connection object using the connection string
    return psycopg2.connect(conn_str)


def upsert_article(doc: Dict[str, Any]) -> None:
    """Insert or update a news article row.

    Expects `doc` to contain at least:
      - site: str
      - category: str
      - url: str
      - title: Optional[str]
      - lang: str (e.g. "hi")
      - text: str  (full Hindi content)
      - scraped_at: ISO8601 string or datetime acceptable to PostgreSQL
      - meta: dict (will be stored as JSONB)

    The corresponding `news_articles` table should roughly be:

        CREATE TABLE news_articles (
          id           BIGSERIAL PRIMARY KEY,
          site         TEXT        NOT NULL,
          category     TEXT        NOT NULL,
          url          TEXT        NOT NULL UNIQUE,
          title        TEXT,
          lang         TEXT        NOT NULL,
          content_hi   TEXT        NOT NULL,
          scraped_at   TIMESTAMPTZ NOT NULL,
          published_at TIMESTAMPTZ,
          meta         JSONB
        );
    """
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # Ensure the table exists before inserting.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_articles (
                      id           BIGSERIAL PRIMARY KEY,
                      site         TEXT        NOT NULL,
                      category     TEXT        NOT NULL,
                      url          TEXT        NOT NULL UNIQUE,
                      title        TEXT,
                      lang         TEXT        NOT NULL,
                      content_hi   TEXT        NOT NULL,
                      scraped_at   TIMESTAMPTZ NOT NULL,
                      published_at TIMESTAMPTZ,
                      meta         JSONB
                    );
                    """
                )

                cur.execute(
                    """
                    INSERT INTO news_articles
                      (site, category, url, title, lang, content_hi, scraped_at, meta)
                    VALUES
                      (%(site)s, %(category)s, %(url)s, %(title)s,
                       %(lang)s, %(content_hi)s, %(scraped_at)s, %(meta)s)
                    ON CONFLICT (url) DO UPDATE
                      SET title      = EXCLUDED.title,
                          content_hi = EXCLUDED.content_hi,
                          scraped_at = EXCLUDED.scraped_at,
                          meta       = EXCLUDED.meta;
                    """,
                    {
                        "site": doc["site"],
                        "category": doc["category"],
                        "url": doc["url"],
                        "title": doc.get("title"),
                        "lang": doc.get("lang", "hi"),
                        "content_hi": doc["text"],
                        "scraped_at": doc["scraped_at"],
                        "meta": psycopg2.extras.Json(doc.get("meta", {})),
                    },
                )
    finally:
        conn.close()
