#!/usr/bin/env python3
"""
Example site crawler module.
Exposes a `run(config_path)` entrypoint.
"""
import yaml
from pathlib import Path


def run(config_path):
    """
    Main entrypoint for the example_site crawler.
    :param config_path: path to the site-specific YAML config.
    """
    print(f"[example_site] Starting crawl. Config: {config_path}")
    
    # Load site config if provided
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    
    # TODO: Implement crawl logic
    # 1. Fetch pages from the site (requests, Selenium, etc.)
    # 2. Write raw HTML/markdown to data/raw/example_site/
    # 3. Write metadata (URL, timestamp, etc.) to data/raw_meta/example_site/
    
    print("[example_site] Crawl complete (no-op for now).")


if __name__ == "__main__":
    # Allow running this crawler standalone
    run("configs/example_site.yaml")
