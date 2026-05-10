"""
FastAPI application — /search and /health endpoints.

POST /search  — symptom → NER → MedlinePlus → pgvector → BioMistral screen → ranked results
GET  /health  — liveness probe

Run: uvicorn serving.api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline.search import SearchPipeline
from serving.cache import ResponseCache

logger = logging.getLogger(__name__)

# ── Request / Response models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    symptoms: str = Field(..., min_length=3, max_length=2000)
    max_results: int = Field(default=5, ge=1, le=20)
    status_filter: str = Field(default="RECRUITING")


class ScreeningResultOut(BaseModel):
    nct_id: str
    title: str
    eligible: bool
    confidence: float
    reason: str
    key_criteria_met: list[str]
    key_criteria_failed: list[str]
    url: str
    latency_ms: float


class SearchResponse(BaseModel):
    query_id: str
    normalized_condition: str
    candidates_retrieved: int
    results: list[ScreeningResultOut]
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    model: str
    version: str
    cache_ok: bool


# ── App setup ─────────────────────────────────────────────────────────────────

_pipeline: SearchPipeline | None = None
_cache: ResponseCache | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _pipeline, _cache
    _pipeline = SearchPipeline()
    _cache = ResponseCache()
    logger.info("SearchPipeline and ResponseCache initialized")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Clinical Trial Search API",
    version="1.0.0",
    description="AI-powered clinical trial eligibility screening",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    assert _pipeline is not None and _cache is not None

    cached = _cache.get(request.symptoms, request.status_filter, request.max_results)
    if cached:
        logger.info("Cache hit for query: %.50s", request.symptoms)
        return SearchResponse(**cached)

    start = time.monotonic()
    try:
        pipeline_result = _pipeline.run(
            symptoms=request.symptoms,
            max_results=request.max_results,
            status_filter=request.status_filter,
        )
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail="Search pipeline failed") from exc

    total_ms = (time.monotonic() - start) * 1000

    results_out = [
        ScreeningResultOut(
            nct_id=r.nct_id,
            title=r.title,
            eligible=r.eligible,
            confidence=r.confidence,
            reason=r.reason,
            key_criteria_met=r.key_criteria_met,
            key_criteria_failed=r.key_criteria_failed,
            url=f"https://clinicaltrials.gov/study/{r.nct_id}",
            latency_ms=r.latency_ms,
        )
        for r in pipeline_result["results"]
    ]

    response = SearchResponse(
        query_id=str(uuid.uuid4()),
        normalized_condition=pipeline_result["normalized_condition"],
        candidates_retrieved=pipeline_result["candidates_retrieved"],
        results=results_out,
        latency_ms=total_ms,
    )

    _cache.set(
        request.symptoms,
        request.status_filter,
        request.max_results,
        response.model_dump(),
    )
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    cache_ok = _cache.ping() if _cache else False
    return HealthResponse(
        status="ok",
        model="BioMistral-7B-QLoRA",
        version="1.0.0",
        cache_ok=cache_ok,
    )
