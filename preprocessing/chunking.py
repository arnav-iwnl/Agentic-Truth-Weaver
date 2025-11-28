"""Document chunking utilities."""
from typing import List, Dict, Any


def simple_chunk(text: str, max_tokens: int = 512) -> List[str]:
    """Naive chunking by words; treat max_tokens as max words for now."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_tokens):
        chunks.append(" ".join(words[i : i + max_tokens]))
    return chunks


def chunk_document(doc: Dict[str, Any], max_tokens: int = 512) -> List[Dict[str, Any]]:
    chunks = simple_chunk(doc["text"], max_tokens=max_tokens)
    return [
        {"id": f"{doc['id']}::chunk_{i}", "text": chunk, "meta": {**doc.get("meta", {}), "chunk_index": i}}
        for i, chunk in enumerate(chunks)
    ]
