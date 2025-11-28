#!/usr/bin/env python3
"""Aaj Tak crawler.

Fetch sitemap (using AsyncWebCrawler), extract URLs robustly, and scrape pages.
Outputs are organized by site and by news category:
- Raw markdown under: data/raw/aaj_tak/<category>/
- Metadata under: data/raw_meta/aaj_tak/<category>/

The module exposes a `run(config_path)` entrypoint so it can be orchestrated
via `crawlers/run_crawlers.py`. The optional YAML config can override defaults
such as sitemap URL and output roots.
"""
import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import yaml
from crawl4ai import AsyncWebCrawler

# -------- DEFAULT CONFIG --------
SITE_NAME_DEFAULT = "aaj_tak"
SITEMAP_URL_DEFAULT = "https://www.aajtak.in/rssfeeds/news-sitemap.xml"
CONCURRENCY_DEFAULT = 4
MAX_RETRIES_DEFAULT = 3
BASE_BACKOFF_DEFAULT = 1.0
SITEMAP_PREVIEW_CHARS = 800


class CrawlerSettings:
    def __init__(self, raw: Dict[str, Any]):
        site_name = raw.get("site_name", SITE_NAME_DEFAULT)
        self.site_name: str = site_name
        self.sitemap_url: str = raw.get("sitemap_url", SITEMAP_URL_DEFAULT)
        self.concurrency: int = int(raw.get("concurrency", CONCURRENCY_DEFAULT))
        self.max_retries: int = int(raw.get("max_retries", MAX_RETRIES_DEFAULT))
        self.base_backoff: float = float(raw.get("base_backoff", BASE_BACKOFF_DEFAULT))

        # Root dirs – we add per-category subdirs at write time
        raw_root = raw.get("output_raw_dir", f"data/raw/{site_name}")
        meta_root = raw.get("output_meta_dir", f"data/raw_meta/{site_name}")
        self.raw_root = raw_root
        self.meta_root = meta_root

        # Per-site progress / log files
        self.progress_file = raw.get("progress_file", os.path.join(meta_root, "pages_done.json"))
        self.log_file = raw.get("log_file", os.path.join(meta_root, "pages_failures.log"))

        # Ensure base dirs exist; category subdirs will be created later
        os.makedirs(self.raw_root, exist_ok=True)
        os.makedirs(self.meta_root, exist_ok=True)


# Settings are bound at runtime by run()/main()
SETTINGS: Optional[CrawlerSettings] = None
SEM: Optional[asyncio.Semaphore] = None


# -------- Helpers --------
def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def url_to_fname(url: str) -> str:
    h = sha1(url.encode("utf-8")).hexdigest()[:12]
    nice = url.replace("https://", "").replace("http://", "").replace("/", "_")
    nice = (nice[:60] + "...") if len(nice) > 60 else nice
    return f"{nice}_{h}"


def extract_category(url: str) -> str:
    """Infer a category slug from the URL path.

    For Aaj Tak URLs, the first non-empty path segment usually reflects the
    section (e.g., `india-news`, `world-news`). We sanitize that segment for
    safe filesystem usage. If no reasonable segment exists, we fall back to
    `uncategorized`.
    """
    parsed = urlparse(url)
    path = (parsed.path or "/").strip("/")
    if not path:
        return "uncategorized"
    first = path.split("/")[0].lower()
    # Keep alnum, dash, underscore; map others to `_`
    first = re.sub(r"[^a-z0-9_-]+", "_", first).strip("_")
    return first or "uncategorized"


def load_progress(settings: CrawlerSettings) -> Set[str]:
    if os.path.exists(settings.progress_file):
        try:
            with open(settings.progress_file, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_progress(settings: CrawlerSettings, done_set: Set[str]):
    tmp = settings.progress_file + ".tmp"
    os.makedirs(os.path.dirname(settings.progress_file), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(list(done_set), f, indent=2)
    os.replace(tmp, settings.progress_file)


def log_failure(settings: CrawlerSettings, url: str, error: str):
    os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
    with open(settings.log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {url}  |  {error}\n")


async def retry_async(fn, *args, max_retries: int, base_backoff: float, **kwargs):
    attempt = 0
    while True:
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            attempt += 1
            if attempt >= max_retries:
                raise
            backoff = base_backoff * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)


# -------- Robust sitemap parsing --------
def debug_preview(sitemap_xml: str, n: int = SITEMAP_PREVIEW_CHARS):
    print(f"(sitemap length = {len(sitemap_xml)} bytes)")
    print("=== SITEMAP PREVIEW ===")
    print(sitemap_xml[:n])
    print("=======================")


def extract_urls_from_sitemap_robust(xml_text: str) -> List[str]:
    """Robust sitemap <loc> extraction.

    Strategy:
      1) Try namespace-aware parse.
      2) Try parse without namespaces.
      3) Try generic `.iter()` to find tags ending with `loc`.
      4) Fallback regex handling CDATA and plain <loc> tags.
    """
    urls: List[str] = []

    if not xml_text or len(xml_text) < 20:
        return urls

    debug_preview(xml_text, n=SITEMAP_PREVIEW_CHARS)

    # 1) namespace-aware parse
    try:
        root = ET.fromstring(xml_text)
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        found = root.findall("ns:url", ns)
        if found:
            for url_tag in found:
                loc = url_tag.find("ns:loc", ns)
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
            if urls:
                return urls
    except Exception:
        pass

    # 2) parse without namespaces
    try:
        root = ET.fromstring(xml_text)
        found = root.findall("url")
        if found:
            for url_tag in found:
                loc = url_tag.find("loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
            if urls:
                return urls
    except Exception:
        pass

    # 3) generic iteration: match tags ending with 'loc'
    try:
        root = ET.fromstring(xml_text)
        for el in root.iter():
            if el.tag and str(el.tag).lower().endswith("loc"):
                if el.text:
                    urls.append(el.text.strip())
        if urls:
            return urls
    except Exception:
        pass

    # 4) fallback regex: handles CDATA and plain <loc> tags
    regex = re.compile(r"<loc>\s*(?:<!\[CDATA\[\s*)?(https?://[^<\]\s]+)(?:\s*\]\]>)?\s*</loc>", re.IGNORECASE)
    found = regex.findall(xml_text)
    seen = set()
    clean: List[str] = []
    for u in found:
        u = u.strip()
        if u not in seen:
            seen.add(u)
            clean.append(u)
    return clean


# -------- Fetch sitemap via AsyncWebCrawler --------
async def fetch_sitemap_via_crawler(url: str, crawler: AsyncWebCrawler, settings: CrawlerSettings) -> str:
    res = await retry_async(
        crawler.arun,
        url=url,
        max_retries=settings.max_retries,
        base_backoff=settings.base_backoff,
    )
    xml_text = getattr(res, "html", "") or ""
    if not xml_text:
        raise RuntimeError("Empty sitemap response from crawler.")
    return xml_text


# -------- Scrape single page --------
async def scrape_single_page(crawler: AsyncWebCrawler, url: str, done_set: Set[str], settings: CrawlerSettings):
    global SEM
    if url in done_set:
        return

    if SEM is None:
        SEM = asyncio.Semaphore(settings.concurrency)

    async with SEM:
        try:
            result = await retry_async(
                crawler.arun,
                url=url,
                max_retries=settings.max_retries,
                base_backoff=settings.base_backoff,
            )

            # Extract markdown (string or object) or fall back to html/extracted_content
            md = ""
            if getattr(result, "markdown", None):
                md_field = result.markdown
                if isinstance(md_field, str):
                    md = md_field
                else:
                    md = getattr(md_field, "raw_markdown", None) or getattr(md_field, "fit_markdown", None) or ""
            if not md:
                md = getattr(result, "extracted_content", None) or getattr(result, "html", "") or ""

            category = extract_category(url)

            output_dir = os.path.join(settings.raw_root, category)
            meta_dir = os.path.join(settings.meta_root, category)
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(meta_dir, exist_ok=True)

            fname = url_to_fname(url)
            md_path = os.path.join(output_dir, f"{fname}.md")
            meta_path = os.path.join(meta_dir, f"{fname}.json")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md or "")

            # Metadata enriched with site + category
            base_meta: Dict[str, Any] = getattr(result, "metadata", {}) or {}
            metadata = {
                "url": url,
                "title": getattr(result, "title", None) or base_meta.get("title"),
                "lang": getattr(result, "language", None),
                "status_code": getattr(result, "status_code", None),
                "site": settings.site_name,
                "category": category,
                "timestamp": now_iso(),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            print(f"✔ Saved: {md_path}")

            done_set.add(url)
            save_progress(settings, done_set)

        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            log_failure(settings, url, str(e))


# -------- Orchestrator --------
async def scrape_urls_from_sitemap(settings: CrawlerSettings):
    done = load_progress(settings)

    async with AsyncWebCrawler() as crawler:
        print(f"Fetching sitemap via AsyncWebCrawler: {settings.sitemap_url}")
        sitemap_xml = await fetch_sitemap_via_crawler(settings.sitemap_url, crawler, settings)

        urls = extract_urls_from_sitemap_robust(sitemap_xml)
        print(f"Found {len(urls)} URLs in sitemap. (Already done: {len(done)})")

        if not urls:
            print("No URLs found. Exiting.")
            return

        to_process = [u for u in urls if u not in done]
        print(f"Will process {len(to_process)} new pages.")

        tasks = [scrape_single_page(crawler, u, done, settings) for u in to_process]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for u, r in zip(to_process, results):
            if isinstance(r, Exception):
                log_failure(settings, u, f"Task-level exception: {r}")


# -------- Entry points --------
async def _amain(settings: CrawlerSettings):
    await scrape_urls_from_sitemap(settings)
    print("\n🎉 DONE — all pages processed (or attempted).")


def load_settings_from_yaml(config_path: Optional[str]) -> CrawlerSettings:
    raw: Dict[str, Any] = {}
    if config_path:
        p = Path(config_path)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if not isinstance(loaded, dict):
                    raise ValueError(f"Config at {config_path} must be a mapping.")
                raw.update(loaded)
    return CrawlerSettings(raw)


def run(config_path: Optional[str] = None) -> None:
    """Entry point expected by `crawlers/run_crawlers.py`.

    `config_path` (if provided) should point to a YAML file with keys such as:
      - site_name
      - sitemap_url
      - output_raw_dir
      - output_meta_dir
      - concurrency, max_retries, base_backoff
    """
    settings = load_settings_from_yaml(config_path)
    global SETTINGS, SEM
    SETTINGS = settings
    SEM = None  # reset per run
    asyncio.run(_amain(settings))


async def main() -> None:
    """CLI-friendly async entrypoint using default settings or `configs/aaj_tak.yaml`.

    If `configs/aaj_tak.yaml` exists, it is used; otherwise defaults are applied.
    """
    cfg_path = None
    default_cfg = Path("configs/aaj_tak.yaml")
    if default_cfg.exists():
        cfg_path = str(default_cfg)
    settings = load_settings_from_yaml(cfg_path)
    global SETTINGS, SEM
    SETTINGS = settings
    SEM = None
    await _amain(settings)


if __name__ == "__main__":
    asyncio.run(main())
