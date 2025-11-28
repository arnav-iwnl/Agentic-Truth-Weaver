"""Batch worker: read processed documents, chunk them, and generate embeddings."""
from pathlib import Path
from typing import Dict, Any
import json

from preprocessing.chunking import chunk_document
from embeddings.embedder import embed_texts


def run(config: Dict[str, Any]) -> None:
    """Embeddings batch worker entrypoint.

    Expected config keys:
      - processed_dir
      - output_dir
    """
    processed_dir = Path(config.get("processed_dir", "data/processed"))
    output_dir = Path(config.get("output_dir", "data/processed")) / "embedded"
    output_dir.mkdir(parents=True, exist_ok=True)

    for doc_path in processed_dir.glob("*.json"):
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        chunks = chunk_document(doc)
        texts = [c["text"] for c in chunks]
        vectors = embed_texts(texts)
        out_path = output_dir / f"{doc_path.stem}_vectors.json"
        out_path.write_text(json.dumps({"chunks": chunks, "vectors": vectors}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run({})
