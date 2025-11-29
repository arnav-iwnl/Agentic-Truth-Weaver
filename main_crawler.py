#!/usr/bin/env python3
"""Main crawler runner for Aaj Tak and The Hindu.

Run from the repo root, for example:

    python main_crawler.py

This will:
  1. Run the Aaj Tak sitemap-based crawler.
  2. Run The Hindu RSS-based crawler.

Both crawlers accept an optional YAML config path. If the corresponding
configs (``configs/aaj_tak.yaml`` and ``configs/the_hindu.yaml``) exist,
this script will pass them through; otherwise, each crawler falls back
to its internal defaults.
"""
from __future__ import annotations

from pathlib import Path
import sys


# Ensure project root is on sys.path so that local packages (e.g. "crawlers")
# are importable when this file is executed as a script.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawlers.aaj_tak import crawl as aaj_tak_crawl
from crawlers.the_hindu import crawl as hindu_crawl


def main() -> None:
    """Run both news crawlers in sequence."""
    cfg_dir = ROOT / "configs"

    aaj_cfg = cfg_dir / "aaj_tak.yaml"
    hindu_cfg = cfg_dir / "the_hindu.yaml"

    print("[main_crawler] Running Aaj Tak crawler...")
    aaj_tak_crawl.run(str(aaj_cfg) if aaj_cfg.exists() else None)

    print("[main_crawler] Running The Hindu crawler...")
    hindu_crawl.run(str(hindu_cfg) if hindu_cfg.exists() else None)

    print("[main_crawler] Done running crawlers.")


if __name__ == "__main__":
    main()
