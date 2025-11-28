"""Ingestion pipeline: convert raw pages into structured documents under data/processed/.
Config-first, idempotent design: running twice on same inputs should not duplicate work.
"""
from pathlib import Path
from typing import Iterable, Dict, Any
import json


def load_raw_pages(raw_dir: str) -> Iterable[Dict[str, Any]]:
    """Yield raw pages and metadata from data/raw and data/raw_meta."""
    raw_path = Path(raw_dir)
    for html_file in raw_path.glob("*.html"):
        yield {"path": str(html_file), "content": html_file.read_text(encoding="utf-8"), "meta": {}}


def process_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw page into a structured document.

    This is deliberately minimal; extend with real parsing and normalization.
    """
    return {
        "id": page["path"],
        "text": page["content"],
        "meta": page.get("meta", {}),
    }


def run(config: Dict[str, Any]) -> None:
    """Ingestion entrypoint.

    Expected config keys:
      - raw_dir
      - output_dir
    """
    raw_dir = config.get("raw_dir", "data/raw/example_site")
    output_dir = Path(config.get("output_dir", "data/processed"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for page in load_raw_pages(raw_dir):
        doc = process_page(page)
        out_path = output_dir / (Path(doc["id"]).stem + ".json")
        # Idempotent: overwrite by doc id
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run({})
