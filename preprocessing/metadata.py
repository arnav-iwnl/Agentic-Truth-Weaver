"""Metadata helpers for enriching documents and chunks."""
from typing import Dict, Any


def add_site_metadata(doc: Dict[str, Any], site_name: str) -> Dict[str, Any]:
    meta = {**doc.get("meta", {}), "site": site_name}
    return {**doc, "meta": meta}
