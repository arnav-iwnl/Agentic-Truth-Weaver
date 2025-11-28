#!/usr/bin/env python3
"""
Orchestrator that reads configs/sites.yaml and dispatches to site-specific crawlers.
Each crawler is expected to have a `run(config_path)` entrypoint.
"""
import yaml
import importlib
import sys
from pathlib import Path


def load_sites_config(path="configs/sites.yaml"):
    """Load site definitions from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("sites", {})


def run_crawler_for_site(site_name, site_config):
    """Dynamically import and run the site's crawler."""
    if not site_config.get("enabled", False):
        print(f"[INFO] {site_name} is disabled; skipping.")
        return
    
    module_path = site_config.get("crawler_module")
    if not module_path:
        print(f"[ERROR] No crawler_module specified for {site_name}.")
        return
    
    config_path = site_config.get("config_path")
    if not config_path:
        print(f"[WARN] No config_path specified for {site_name}; crawler may fail.")
    
    print(f"[INFO] Running crawler for {site_name} (module={module_path})...")
    try:
        module = importlib.import_module(module_path)
        if hasattr(module, "run"):
            module.run(config_path)
            print(f"[SUCCESS] {site_name} crawl complete.")
        else:
            print(f"[ERROR] Module {module_path} does not have a `run(config_path)` function.")
    except Exception as e:
        print(f"[ERROR] Failed to run crawler for {site_name}: {e}")


def main():
    """Main orchestrator entrypoint."""
    sites = load_sites_config()
    if not sites:
        print("[WARN] No sites found in configs/sites.yaml.")
        return
    
    for site_name, site_config in sites.items():
        run_crawler_for_site(site_name, site_config)


if __name__ == "__main__":
    main()
