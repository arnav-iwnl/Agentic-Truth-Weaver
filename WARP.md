{
  "query": "latest news on politics",
  "contexts": [
    {
      "id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385::chunk_1",
      "score": 1.0,
      "metadata": {
        "article_id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385",
        "category": "india",
        "chunk_index": 1,
        "section": "india",
        "site": "the_hindu",
        "status_code": 200,
        "timestamp": "2025-11-28T22:13:24.103542Z",
        "title": "CeNS scientists make breakthrough in the development of eco-friendly batteries - The Hindu",
        "url": "https://www.thehindu.com/news/national/karnataka/cens-scientists-make-breakthrough-in-the-development-of-eco-friendly-batteries/article70335424.ece"
      }
    },
    {
      "id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385::chunk_2",
      "score": 1.0,
      "metadata": {
        "article_id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385",
        "category": "india",
        "chunk_index": 2,
        "section": "india",
        "site": "the_hindu",
        "status_code": 200,
        "timestamp": "2025-11-28T22:13:24.103542Z",
        "title": "CeNS scientists make breakthrough in the development of eco-friendly batteries - The Hindu",
        "url": "https://www.thehindu.com/news/national/karnataka/cens-scientists-make-breakthrough-in-the-development-of-eco-friendly-batteries/article70335424.ece"
      }
    },
    {
      "id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385::chunk_3",
      "score": 1.0,
      "metadata": {
        "article_id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385",
        "category": "india",
        "chunk_index": 3,
        "section": "india",
        "site": "the_hindu",
        "status_code": 200,
        "timestamp": "2025-11-28T22:13:24.103542Z",
        "title": "CeNS scientists make breakthrough in the development of eco-friendly batteries - The Hindu",
        "url": "https://www.thehindu.com/news/national/karnataka/cens-scientists-make-breakthrough-in-the-development-of-eco-friendly-batteries/article70335424.ece"
      }
    },
    {
      "id": "news:1::chunk_0",
      "score": 1.0,
      "metadata": {
        "article_id": "1",
        "category": "india",
        "chunk_index": 0,
        "site": "aaj_tak",
        "status_code": 200,
        "timestamp": "2025-11-28T18:37:02.362829Z",
        "title": "मंत्री जगह सिंह नेगी की RSS पर टिप्पणी को लेकर हिमाचल विधानसभा में BJP सदस्यों का हंगामा - BJP members create ruckus in Himachal Assembly over Minister Jagan Singh Negi's remarks on RSS ntc - AajTak",
        "url": "https://www.aajtak.in/india/himachal-pradesh/story/bjp-members-create-ruckus-in-himachal-assembly-over-minister-jagan-singh-negis-remarks-on-rss-ntc-dskc-2399068-2025-11-28"
      }
    },
    {
      "id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385::chunk_0",
      "score": 1.0,
      "metadata": {
        "article_id": "the_hindu/india/www.thehindu.com_news_national_karnataka_cens-scientists-mak..._9ccfbf6bd385",
        "category": "india",
        "chunk_index": 0,
        "section": "india",
        "site": "the_hindu",
        "status_code": 200,
        "timestamp": "2025-11-28T22:13:24.103542Z",
        "title": "CeNS scientists make breakthrough in the development of eco-friendly batteries - The Hindu",
        "url": "https://www.thehindu.com/news/national/karnataka/cens-scientists-make-breakthrough-in-the-development-of-eco-friendly-batteries/article70335424.ece"
      }
    }
  ],
  "answer": "Stub answer for: latest news on politics"
}


# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

This repository implements a simple orchestration pipeline for a news-focused Retrieval-Augmented Generation (RAG) system. It is structured as a set of small, composable Python modules that:

1. Crawl news sites into a local `data/` directory.
2. Ingest raw pages into structured JSON documents.
3. Preprocess and chunk documents.
4. Generate embeddings for chunks.
5. (Stub) Persist vectors to a vector database.
6. (Stub) Expose a FastAPI-based `/query` endpoint that calls a RAG runner.

Most components are currently minimal stubs intended to be extended.

## Architecture and Data Flow

### High-level pipeline

1. **Crawling (HTML capture)**
   - Entry: `crawlers/run_crawlers.py`.
   - Reads `configs/sites.yaml`, then dynamically imports per-site crawler modules (e.g. `crawlers.example_site.crawl`).
   - Each crawler exposes a `run(config_path)` function and is expected to write raw content under `data/raw/<site_name>/` and metadata under `data/raw_meta/<site_name>/` (see comments in `crawlers/example_site/crawl.py`).

2. **Ingestion (raw → processed documents)**
   - Entry: `ingestion/processor.py`.
   - `run(config)` reads HTML files from `config["raw_dir"]` (default `data/raw/example_site`) and writes normalized JSON docs to `config["output_dir"]` (default `data/processed`).
   - Docs are simple dictionaries `{id, text, meta}`; file naming is derived from the raw path stem, making the process idempotent.

3. **Preprocessing (chunking/cleaning/metadata)**
   - `preprocessing/chunking.py`:
     - `simple_chunk(text, max_tokens)` splits text into word-based chunks.
     - `chunk_document(doc, max_tokens)` produces chunk dicts with chunk-specific metadata and ids of the form `"<doc_id>::chunk_<i>"`.
   - `preprocessing/cleaners.py`: basic text normalization helpers.
   - `preprocessing/metadata.py`: utilities for enriching docs with site-level metadata.
   - Currently, chunking is wired into embeddings; cleaning/metadata helpers are designed for future integration into ingestion or embedding stages.

4. **Embeddings (processed → chunk vectors)**
   - Entry: `embeddings/batch_worker.py`.
   - `run(config)` reads processed JSON documents from `config["processed_dir"]` (default `data/processed`), calls `chunk_document`, and embeds chunk texts via `embeddings.embedder.embed_texts`.
   - Output is written under `Path(config["output_dir"] or "data/processed") / "embedded"` as `*_vectors.json` containing `{ "chunks": [...], "vectors": [...] }`.
   - `embeddings/embedder.py` is a backend-agnostic stub; `embed_texts` currently returns a trivial vector derived from text length and is the main extension point for integrating a real model (OpenAI, local embedding model, etc.).

5. **Vector database (stub)
   - `vector_db/client.py` defines `VectorDBClient` with an `upsert(ids, vectors, metadatas)` method that currently just logs a message. This is the intended abstraction point for integrating with Chroma, Pinecone, or other vector stores.

6. **Retrieval and RAG orchestration**
   - `retrieval/retriever.py`:
     - `Retriever` encapsulates retrieval logic; for now, `query(query_text, top_k)` logs the query and returns an empty list.
     - `from_config(config)` builds a `Retriever` from a retrieval config dict.
   - `retrieval/rag_runner.py`:
     - `run_rag(query, config)` builds a retriever via `retriever.from_config(config["retrieval"])`, calls `retriever.query`, and returns a dict with `query`, `contexts`, and a stub `answer` string.
     - LLM integration is deliberately omitted and should be added here.

7. **API layer (FastAPI)
   - `api/app.py` defines a `FastAPI` app titled "News RAG Orchestrator".
   - Endpoints:
     - `GET /health` → `{"status": "ok"}`.
     - `POST /query` accepts body `{ "query": <str> }`, constructs a minimal `config` (currently `{ "retrieval": {} }`), and calls `run_rag(query, config)`.
   - Config loading is currently a TODO; when wiring in real configuration, prefer to keep the API layer thin and delegate orchestration and defaults to `rag_runner` and downstream modules.

8. **Configuration and data layout**
   - `configs/`:
     - `sites.yaml` lists sites and their crawler modules plus optional `config_path` and `schedule`.
     - `example_site.yaml` holds crawler-specific options such as `base_url`, crawl patterns, and output directories for raw content/metadata.
   - `data/` (directory only, no code): intended to hold all runtime artifacts:
     - `data/raw/<site_name>/` – raw HTML/markdown.
     - `data/raw_meta/<site_name>/` – metadata for raw pages.
     - `data/processed/` – normalized JSON documents.
     - `data/processed/embedded/` – chunk + vector payloads emitted by the embeddings worker.

## Common Commands

Assume you are in the repository root (`news_rag_orchestrator/`) so that relative paths in the code (e.g., `configs/`, `data/`) resolve correctly.

### Crawl all configured sites

```bash path=null start=null
python crawlers/run_crawlers.py
```

- Reads `configs/sites.yaml` and runs each site whose `enabled` flag is `true`.
- Site-specific crawler modules must expose `run(config_path)`; see `crawlers/example_site/crawl.py` for the reference pattern.

### Run the example crawler directly

```bash path=null start=null
python crawlers/example_site/crawl.py
```

- Uses `configs/example_site.yaml` (see the `__main__` guard in that file) and currently behaves as a no-op stub that logs progress.

### Ingest raw pages into processed JSON

```bash path=null start=null
python ingestion/processor.py
```

- Uses defaults `raw_dir="data/raw/example_site"` and `output_dir="data/processed"`.
- To customize behavior, import `ingestion.processor.run` from a script or REPL and pass a config dict.

### Generate embeddings for processed documents

```bash path=null start=null
python embeddings/batch_worker.py
```

- Uses `processed_dir="data/processed"` and writes embedded outputs under `data/processed/embedded/`.
- Extend `embeddings/embedder.py` to plug in a real embedding backend; the worker entrypoint does not need to change.

### Run the API server (FastAPI)

There is no dedicated runner script, but `api/app.py` exposes a standard FastAPI app instance named `app`. With `uvicorn` installed, you can run:

```bash path=null start=null
uvicorn api.app:app --reload
```

- This exposes `/health` and `/query`.
- Because imports like `from retrieval.rag_runner import run_rag` assume the repo root is on `PYTHONPATH`, run this command from the repository root.

## Testing and Linting

- There are currently **no tests** or linting/formatting configurations checked into this repository (no `pytest`/`unittest` modules, `pyproject.toml`, or lint configs).
- When you introduce a test suite or tooling (e.g., `pytest`, `ruff`, `black`, `mypy`), update this section with the canonical commands (including how to run a single test) and prefer using those consistently across future changes.

## Implementation Notes for Future Changes

- **Config-driven design**: Many entrypoints accept a `config: Dict[str, Any]` or depend on YAML configs under `configs/`. When adding features, prefer extending config structures rather than hard-coding values in code.
- **Idempotency**: Ingestion and embedding stages are written to be safe to rerun (overwriting outputs by id). Preserve this property where possible when evolving the pipeline.
- **Separation of concerns**:
  - Keep crawlers focused on fetching and writing raw content/metadata.
  - Keep ingestion focused on normalization and document shaping.
  - Keep preprocessing/embeddings focused on text transformation and vectorization.
  - Keep retrieval and RAG orchestration in `retrieval/` and `api/` thin and delegating.
