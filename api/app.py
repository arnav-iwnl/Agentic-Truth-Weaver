"""API layer exposing /query and /health endpoints."""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any

from retrieval.rag_runner import run_rag


app = FastAPI(title="News RAG Orchestrator")


class QueryRequest(BaseModel):
    query: str


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
async def query(req: QueryRequest) -> Dict[str, Any]:
    config: Dict[str, Any] = {"retrieval": {}}  # TODO: load from config files
    result = run_rag(req.query, config)
    return result
