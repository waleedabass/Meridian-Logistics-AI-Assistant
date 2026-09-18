# FastAPI app
# run with: uvicorn app.main:app --port 8000

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.qa import QAService
from app.retrieval import Index

log = logging.getLogger("uvicorn.error")

# filled in on startup
index = None
qa = None
has_api_key = False


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class Source(BaseModel):
    document: str
    location: str
    snippet: str
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    document_status: Optional[str] = None
    extraction: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    latency_ms: int
    # extra fields (not in the spec) - handy for the eval script and debugging
    status: str
    model: str
    mode: str
    usage: dict
    cost_usd: float


@asynccontextmanager
async def lifespan(app):
    global index, qa, has_api_key

    if not config.INDEX_PATH.exists():
        raise RuntimeError(f"No index at {config.INDEX_PATH}. Run: python -m app.ingest")
    index = Index(config.INDEX_PATH)
    qa = QAService(index)
    log.info("Loaded %d chunks from %d documents; mode=%s model=%s context~%d tokens",
             len(index.chunks), len(index.documents), qa.mode, qa.model, index.full_context_tokens_estimate)

    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if not has_api_key:
        log.warning("ANTHROPIC_API_KEY is not set: /ask will return 500 until it is added to .env")
    elif os.getenv("PREWARM", "1") == "1":
        # send one question on startup so the prompt cache is already filled
        # when the first real user asks something
        try:
            a = await qa.ask("What documents are available?")
            log.info("Prompt cache warmed in %d ms (cache write %d tokens)", a.latency_ms,
                     a.usage.cache_creation_input_tokens)
        except Exception as e:
            log.warning("Warm-up call failed: %s", e)
    yield


app = FastAPI(title="Meridian Logistics Knowledge Assistant", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "api_key_configured": has_api_key, "model": qa.model, "mode": qa.mode,
            "chunks": len(index.chunks), "index_built_at": index.built_at}


@app.get("/documents")
async def documents():
    fields = ["file", "title", "meta_line", "status", "superseded_by", "pages",
              "ocr_pages", "tables", "blocks_removed_as_duplicates"]
    result = []
    for doc in index.documents.values():
        result.append({f: doc[f] for f in fields})
    return result


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    if not has_api_key:
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
        answer=a.answer,
        sources=a.sources,
        latency_ms=a.latency_ms,
        status=a.status,
        model=a.model,
        mode=a.mode,
        usage=a.usage.__dict__,
        cost_usd=a.usage.cost_usd(a.model),
    )
