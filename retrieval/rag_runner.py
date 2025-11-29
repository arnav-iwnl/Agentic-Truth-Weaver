"""RAG runner: orchestrates retrieval + LLM to produce answers."""
from typing import Dict, Any

from retrieval.retriever import from_config as retriever_from_config
from llm.agentic_truth_model import analyze_query


def run_rag(query: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run retrieval and pass results to the agentic truth model.

    Steps:
      1. Use retriever to fetch context docs (from Pinecone).
      2. Call the Gemini-based agentic model with query + contexts.
    """
    retriever = retriever_from_config(config.get("retrieval", {}))
    contexts = retriever.query(query, top_k=config.get("top_k", 5))

    # Delegate all higher-level reasoning to the agentic model.
    return analyze_query(query, contexts)
