"""Vector database client abstraction.

Currently implements a Pinecone-backed client.

Configuration (via dict passed to ``from_config``):
  - api_key: Optional[str] (default: environment variable ``PINECONE_API_KEY``)
  - index_name: str (default: "news-embeddings")
  - dimension: int  -- required when creating a new index
  - metric: str (default: "cosine")
  - cloud: str (default: "aws")
  - region: str (default: "us-east-1")
"""
from __future__ import annotations

import os
from typing import List, Dict, Any
from dotenv import load_dotenv

from pinecone import Pinecone, ServerlessSpec
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY","pcsk_E3uNY_FKzFJvfXNgsXKLdbsWa3vbVfaBv7F5Q6F6zTMHfrn3osgRTgXQEDmtFMJCdCnmC")

class VectorDBClient:
    """Thin wrapper around a Pinecone index.

    The first call to ``from_config`` will ensure that the configured index exists,
    creating it if necessary.
    """

    def __init__(self, config: Dict[str, Any]):
        API_KEY = PINECONE_API_KEY
        if not  API_KEY:
            raise ValueError(
                "Pinecone API key is required; set PINECONE_API_KEY env var or "
                "provide config['api_key']."
            )

        self._pc = Pinecone(api_key=API_KEY)

        self.index_name: str = config.get("index_name", "news-embeddings")
        metric: str = config.get("metric", "cosine")
        cloud: str = config.get("cloud", "aws")
        region: str = config.get("region", "us-east-1")

        existing_index_names = {idx.name for idx in self._pc.list_indexes()}

        if self.index_name not in existing_index_names:
            # Need to create the index. ``dimension`` must be supplied in config.
            dimension = config.get("dimension")
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError(
                    "config['dimension'] (positive int) is required to create a new "
                    "Pinecone index."
                )

            self._pc.create_index(
                name=self.index_name,
                dimension=dimension,
                metric=metric,
                spec=ServerlessSpec(cloud=cloud, region=region),
            )

        self._index = self._pc.Index(self.index_name)

    def upsert(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Upsert vectors into the Pinecone index.

        ``ids``, ``vectors``, and ``metadatas`` must be the same length.
        """
        if not (len(ids) == len(vectors) == len(metadatas)):
            raise ValueError("ids, vectors, and metadatas must have the same length")

        items = [
            {"id": _id, "values": vec, "metadata": meta}
            for _id, vec, meta in zip(ids, vectors, metadatas)
        ]

        if not items:
            return

        self._index.upsert(vectors=items)


def from_config(config: Dict[str, Any]) -> VectorDBClient:
    """Factory used by the rest of the codebase.

    ``config`` is expected to be a flat dict as described in the module docstring.
    """
    return VectorDBClient(config)
