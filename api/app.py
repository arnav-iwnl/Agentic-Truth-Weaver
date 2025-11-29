"""API layer exposing /query and /health endpoints."""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any
from pyngrok import ngrok
import uvicorn

# from retrieval.rag_runner import run_rag
from retrieval.rag_runner import run_rag

app = FastAPI(title="News RAG Orchestrator")


class QueryRequest(BaseModel):
    query: str


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
async def query(req: QueryRequest) -> Dict[str, Any]:
    # Minimal inline config: wire retrieval to the same Pinecone index used
    # by the sync script. API key is taken from PINECONE_API_KEY env var.
    config: Dict[str, Any] = {
        "retrieval": {
            "vector_db": {
                "index_name": "news-embeddings",
            },
            "top_k_default": 5,
        },
        "top_k": 5,
    }
    result = run_rag(req.query, config)
    return result

if __name__ == "__main__":
    public_url = ngrok.connect(8000)
    print("Public url: ", public_url)
    print("Local url: http://127.0.0.1:8000")
    uvicorn.run(app=app, host="0.0.0.0", port=8000, reload=False)

