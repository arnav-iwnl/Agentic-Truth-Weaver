"""RAG runner: orchestrates retrieval + LLM to produce answers."""
from typing import Dict, Any

from retrieval.retriever import from_config as retriever_from_config


def run_rag(query: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Simple RAG runner.

    Steps:
      1. Use retriever to fetch context docs (from Pinecone).
      2. Call LLM with query + context (still stubbed for now).
    """
    retriever = retriever_from_config(config.get("retrieval", {}))
    contexts = retriever.query(query, top_k=config.get("top_k", 5))

    # TODO: integrate with an actual LLM using the retrieved contexts.
    return {
        "query": query,
        "contexts": contexts,
        "answer": f"Stub answer for: {query}",
    }
