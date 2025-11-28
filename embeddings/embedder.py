"""Embeddings layer: convert chunks into vector embeddings.
Backend-agnostic; plug in OpenAI, local models, etc.
"""
from typing import List


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Dummy embedder; replace with real model calls.

    Idempotent: same text list -> same embedding list.
    """
    return [[float(len(t))] for t in texts]
