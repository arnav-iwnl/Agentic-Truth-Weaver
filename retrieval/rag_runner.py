"""RAG runner: orchestrates retrieval + LLM to produce answers."""
from typing import Dict, Any

from retrieval.retriever import from_config as retriever_from_config


def run_rag(query: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Simple RAG runner stub.

    Steps:
      1. Use retriever to fetch context docs.
      2. Call LLM with query + context (omitted here).
    """
    retriever = retriever_from_config(config.get("retrieval", {}))
    contexts = retriever.query(query, top_k=config.get("top_k", 5))
    # TODO: integrate with an LLM; for now just echo the query and contexts size.
    return {
        "query": query,
        "contexts": contexts,
        "answer": f"Stub answer for: {query}",
    }
