#!/usr/bin/env python3
"""The Hindu RSS crawler.

Crawl The Hindu RSS feeds for India (national) and World news and save each
article as Markdown plus JSON metadata, with per-section directories.

Feeds (defaults):
- India (national):      https://www.thehindu.com/news/national/feeder/default.rss
- World (international): https://www.thehindu.com/news/international/feeder/default.rss

This module exposes a `run(config_path)` entrypoint so it can be orchestrated
via `crawlers/run_crawlers.py`. The optional YAML config can override defaults
such as feeds and output roots.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import Any, Callable, Dict, List, Optional

import yaml
from crawl4ai import AsyncWebCrawler


# ---------- CONFIG MODEL ----------

@dataclass
class HinduCrawlerConfig:
    feeds: Dict[str, str] = field(
        default_factory=lambda: {
            "india": "https://www.thehindu.com/news/national/feeder/default.rss",
            "world": "https://www.thehindu.com/news/international/feeder/default.rss",
        }
    )
    base_output_dir: str = "hindu_pages_by_section"   # per-section markdown
    base_meta_dir: str = "hindu_meta_by_section"      # per-section metadata
    log_file: str = "hindu_failures.log"
    progress_file: str = "hindu_progress.json"        # section -> list of urls

    concurrency_pages: int = 6
    max_retries: int = 3
    base_backoff: float = 1.0
    feed_preview_chars: int = 800

    @classmethod
    def from_yaml(cls, path: Optional[str]) -> "HinduCrawlerConfig":
        if not path:
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        cfg = cls()
        # shallow override of known fields
        if "feeds" in raw and isinstance(raw["feeds"], dict):
            cfg.feeds = {str(k): str(v) for k, v in raw["feeds"].items()}
        if "base_output_dir" in raw:
            cfg.base_output_dir = str(raw["base_output_dir"])
        if "base_meta_dir" in raw:
            cfg.base_meta_dir = str(raw["base_meta_dir"])
        if "log_file" in raw:
            cfg.log_file = str(raw["log_file"])
        if "progress_file" in raw:
            cfg.progress_file = str(raw["progress_file"])
        if "concurrency_pages" in raw:
            cfg.concurrency_pages = int(raw["concurrency_pages"])
        if "max_retries" in raw:
            cfg.max_retries = int(raw["max_retries"])
        if "base_backoff" in raw:
            cfg.base_backoff = float(raw["base_backoff"])
        if "feed_preview_chars" in raw:
            cfg.feed_preview_chars = int(raw["feed_preview_chars"])
        return cfg


# ensure base dirs exist (will be re-used per run)
def ensure_base_dirs(cfg: HinduCrawlerConfig) -> None:
    os.makedirs(cfg.base_output_dir, exist_ok=True)
    os.makedirs(cfg.base_meta_dir, exist_ok=True)


# per-run semaphore will be created in `run()`
PAGE_SEM: Optional[asyncio.Semaphore] = None


# ---------- helpers ----------

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def url_to_fname(url: str) -> str:
    """Create a filesystem-friendly, mostly-stable filename from a URL."""
    h = sha1(url.encode("utf-8")).hexdigest()[:12]
    nice = url.replace("https://", "").replace("http://", "").replace("/", "_")
    nice = (nice[:60] + "...") if len(nice) > 60 else nice
    return f"{nice}_{h}"


def ensure_section_dirs(cfg: HinduCrawlerConfig, section: str):
    out_dir = os.path.join(cfg.base_output_dir, section)
    meta_dir = os.path.join(cfg.base_meta_dir, section)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    return out_dir, meta_dir


def load_progress(cfg: HinduCrawlerConfig) -> Dict[str, List[str]]:
    if os.path.exists(cfg.progress_file):
        try:
            with open(cfg.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # normalise values to lists of strings
                    return {k: list(v) for k, v in data.items()}
        except Exception:
            return {}
    return {}


def save_progress(cfg: HinduCrawlerConfig, progress: Dict[str, List[str]]):
    tmp = cfg.progress_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)
    os.replace(tmp, cfg.progress_file)


def log_failure(cfg: HinduCrawlerConfig, target: str, error: str):
    with open(cfg.log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {target}  |  {error}\n")


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int,
    base_backoff: float,
    **kwargs: Any,
):
    attempt = 0
    while True:
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            attempt += 1
            if attempt >= max_retries:
                raise
            backoff = base_backoff * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)


def debug_preview(text: str, n: int):
    """Print a short preview of feed XML for debugging malformed feeds."""
    print(f"(feed length = {len(text)} bytes)")
    print("=== FEED PREVIEW ===")
    print(text[:n])
    print("====================")


def extract_article_urls_from_feed(xml_text: str, preview_chars: int) -> List[str]:
    """Robust extraction of article links from an RSS feed.

    Matches The Hindu format, e.g.:

        <item>
          <link><![CDATA[ https://www.thehindu.com/news/national/... ]]></link>
        </item>

    Strategy:
    1) Try XML parsing; for each <item>, find its <link>.
    2) Fallback regex: pull out https URLs and filter to thehindu.com.
    """
    urls: List[str] = []

    if not xml_text or len(xml_text) < 20:
        return urls

    # 1) XML parse and walk items/links, ignoring namespaces
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter():
            tag = item.tag or ""
            if tag.endswith("item"):
                for child in item:
                    ctag = child.tag or ""
                    if ctag.endswith("link") and child.text:
                        link = child.text.strip()
                        if link.startswith("http") and "thehindu.com" in link:
                            urls.append(link)
        if urls:
            seen = set()
            out: List[str] = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return out
    except Exception:
        # fall through to regex fallback
        debug_preview(xml_text, n=preview_chars)

    # 2) regex fallback: any thehindu.com URL in the feed
    regex = re.compile(r"https?://[^\s<]+thehindu\.com[^\s<]*", re.IGNORECASE)
    found = regex.findall(xml_text)
    seen = set()
    out: List[str] = []
    for u in found:
        u = u.strip()
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def fetch_text_via_crawler(url: str, crawler: AsyncWebCrawler, cfg: HinduCrawlerConfig) -> str:
    res = await retry_async(
        crawler.arun,
        url=url,
        max_retries=cfg.max_retries,
        base_backoff=cfg.base_backoff,
    )
    text = getattr(res, "html", "") or ""
    if not text:
        raise RuntimeError(f"Empty response from {url}")
    return text


# ---------- scraping single article ----------

async def scrape_article_and_save(
    crawler: AsyncWebCrawler,
    url: str,
    section: str,
    progress: Dict[str, List[str]],
    cfg: HinduCrawlerConfig,
):
    """Crawl one article URL and save markdown + metadata under the section."""
    global PAGE_SEM

    done_list = progress.get(section, [])
    if url in done_list:
        return

    if PAGE_SEM is None:
        PAGE_SEM = asyncio.Semaphore(cfg.concurrency_pages)

    async with PAGE_SEM:
        try:
            result = await retry_async(
                crawler.arun,
                url=url,
                max_retries=cfg.max_retries,
                base_backoff=cfg.base_backoff,
            )

            # Extract markdown (string or object) or fall back to html/extracted_content
            md = ""
            if getattr(result, "markdown", None):
                md_field = result.markdown
                if isinstance(md_field, str):
                    md = md_field
                else:
                    md = (
                        getattr(md_field, "raw_markdown", None)
                        or getattr(md_field, "fit_markdown", None)
                        or ""
                    )
            if not md:
                md = (
                    getattr(result, "extracted_content", None)
                    or getattr(result, "html", "")
                    or ""
                )

            out_dir, meta_dir = ensure_section_dirs(cfg, section)
            fname = url_to_fname(url)
            md_path = os.path.join(out_dir, f"{fname}.md")
            meta_path = os.path.join(meta_dir, f"{fname}.json")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md or "")

            metadata = {
                "url": url,
                "title": getattr(result, "title", None)
                or (getattr(result, "metadata", {}) or {}).get("title"),
                "lang": getattr(result, "language", None),
                "status_code": getattr(result, "status_code", None),
                "timestamp": now_iso(),
                "section": section,
                "site": "the_hindu",
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            print(f"✔ Saved [{section}]: {md_path}")

            # mark done in progress structure
            progress.setdefault(section, [])
            progress[section].append(url)
            save_progress(cfg, progress)

        except Exception as e:  # noqa: BLE001
            print(f"❌ Error scraping {url}: {e}")
            log_failure(cfg, url, str(e))


# ---------- feed orchestrator ----------

async def process_feed(
    crawler: AsyncWebCrawler,
    section: str,
    feed_url: str,
    progress: Dict[str, List[str]],
    cfg: HinduCrawlerConfig,
):
    try:
        print(f"Fetching feed for section '{section}': {feed_url}")
        feed_xml = await fetch_text_via_crawler(feed_url, crawler, cfg)
        urls = extract_article_urls_from_feed(feed_xml, cfg.feed_preview_chars)
        print(f"  -> extracted {len(urls)} article URLs from feed '{section}'")

        done_urls = set(progress.get(section, []))
        to_crawl = [u for u in urls if u not in done_urls]
        print(f"  -> will crawl {len(to_crawl)} new articles for section '{section}'")

        tasks = [
            scrape_article_and_save(crawler, u, section, progress, cfg)
            for u in to_crawl
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for u, r in zip(to_crawl, results):
            if isinstance(r, Exception):
                log_failure(cfg, u, f"Task failed: {r}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Failed to process feed {feed_url} for section '{section}': {e}")
        log_failure(cfg, feed_url, str(e))


# ---------- public entrypoints ----------

async def _main_async(cfg: HinduCrawlerConfig) -> None:
    ensure_base_dirs(cfg)
    progress = load_progress(cfg)  # section -> list(urls done)

    async with AsyncWebCrawler() as crawler:
        tasks = [
            process_feed(crawler, section, url, progress, cfg)
            for section, url in cfg.feeds.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    print("\n🎉 DONE — all feeds processed (or attempted).")


def run(config_path: Optional[str] = None) -> None:
    """Entry point used by `crawlers/run_crawlers.py`.

    `config_path` may point to a YAML file with HinduCrawlerConfig overrides.
    """
    cfg = HinduCrawlerConfig.from_yaml(config_path)
    # Reset semaphore each run
    global PAGE_SEM
    PAGE_SEM = None
    asyncio.run(_main_async(cfg))


if __name__ == "__main__":  # pragma: no cover
    # Allow running directly as a script as well
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else None
    run(cfg_path)
