"""FastAPI service.

    uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.qa import QAService
from app.retrieval import Index

log = logging.getLogger("uvicorn.error")
state: dict = {}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class Source(BaseModel):
    document: str
    location: str
    snippet: str
    section: str | None = None
    chunk_id: str | None = None
    document_status: str | None = None
    extraction: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    latency_ms: int
    # extras beyond the required contract, useful for evaluation and debugging
    status: str
    model: str
    mode: str
    usage: dict
    cost_usd: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.INDEX_PATH.exists():
        raise RuntimeError(f"No index at {config.INDEX_PATH}. Run: python -m app.ingest")
    index = Index(config.INDEX_PATH)
    qa = QAService(index)
    state.update(index=index, qa=qa)
    log.info("Loaded %d chunks from %d documents; mode=%s model=%s context~%d tokens",
             len(index.chunks), len(index.documents), qa.mode, qa.model, index.full_context_tokens_estimate)
    has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    state["has_key"] = has_key
    if not has_key:
        log.warning("ANTHROPIC_API_KEY is not set: /ask will return 500 until it is added to .env")
    elif os.getenv("PREWARM", "1") == "1":
        # Writes the prompt cache so the first real user does not pay the cold-prefix latency.
        try:
            a = await qa.ask("What documents are available?")
            log.info("Prompt cache warmed in %d ms (cache write %d tokens)", a.latency_ms,
                     a.usage.cache_creation_input_tokens)
        except Exception as e:  # warm-up is an optimisation; never block startup on it
            log.warning("Warm-up call failed: %s", e)
    yield


app = FastAPI(title="Meridian Logistics Knowledge Assistant", lifespan=lifespan)


@app.get("/health")
async def health():
    qa: QAService = state["qa"]
    return {"status": "ok", "api_key_configured": state["has_key"], "model": qa.model, "mode": qa.mode, "chunks": len(state["index"].chunks),
            "index_built_at": state["index"].built_at}


@app.get("/documents")
async def documents():
    return [{k: d[k] for k in ("file", "title", "meta_line", "status", "superseded_by", "pages",
                               "ocr_pages", "tables", "blocks_removed_as_duplicates")}
            for d in state["index"].documents.values()]


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    qa: QAService = state["qa"]
    if not state["has_key"]:
        raise HTTPException(500, "Model API key missing: set ANTHROPIC_API_KEY in .env and restart")
    try:
        a = await qa.ask(req.question.strip())
    except anthropic.RateLimitError as e:
        raise HTTPException(503, f"Model rate limited, retry shortly: {e.message}")
    except anthropic.AuthenticationError:
        raise HTTPException(500, "Model API key missing or invalid (set ANTHROPIC_API_KEY in .env)")
    except anthropic.APIConnectionError as e:
        raise HTTPException(502, f"Could not reach the model API: {e}")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Model API error {e.status_code}: {e.message}")
    if a.rejected_citations:
        log.info("Dropped %d unverifiable citation(s) for %r", len(a.rejected_citations), req.question)
    return AskResponse(
        answer=a.answer, sources=a.sources, latency_ms=a.latency_ms, status=a.status,
        model=a.model, mode=a.mode, usage=a.usage.__dict__, cost_usd=a.usage.cost_usd(a.model),
    )
