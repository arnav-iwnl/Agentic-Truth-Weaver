"""Retrieval layer: perform vector search and return context documents.

This implementation uses Pinecone as the backing vector DB and the shared
``embeddings.embedder.embed_texts`` function to embed queries.
"""
from __future__ import annotations

from typing import List, Dict, Any

from embeddings.embedder import embed_texts
from pinecone import Pinecone


API_KEY = "pcsk_E3uNY_FKzFJvfXNgsXKLdbsWa3vbVfaBv7F5Q6F6zTMHfrn3osgRTgXQEDmtFMJCdCnmC"

class Retriever:
    def __init__(self, config: Dict[str, Any]):
        """Create a retriever bound to a Pinecone index.

        Expected config structure (minimal):

            {
              "vector_db": {
                "api_key": "...",              # optional, else PINECONE_API_KEY
                "index_name": "news-embeddings"  # must match sync script
              },
              "top_k_default": 5
            }
        """
        self.config = config

        vdb_conf: Dict[str, Any] = config.get("vector_db", {})
        api_key = API_KEY
        self._pc = Pinecone(api_key=api_key) if api_key else Pinecone()
        index_name = vdb_conf.get("index_name", "news-embeddings")
        self._index = self._pc.Index(index_name)

        self._top_k_default: int = int(config.get("top_k_default", 5))

    def query(self, query_text: str, top_k: int | None = None) -> List[Dict[str, Any]]:
        """Embed ``query_text`` and perform semantic search in Pinecone.

        Returns a list of contexts with metadata and scores.
        """
        if top_k is None:
            top_k = self._top_k_default

        query_vec = embed_texts([query_text])[0]

        result = self._index.query(
            vector=query_vec,
            top_k=top_k,
            include_metadata=True,
        )

        contexts: List[Dict[str, Any]] = []
        for match in result.matches or []:
            meta = match.metadata or {}
            contexts.append(
                {
                    "id": match.id,
                    "score": match.score,
                    "metadata": meta,
                }
            )
        return contexts


def from_config(config: Dict[str, Any]) -> Retriever:
    return Retriever(config)
