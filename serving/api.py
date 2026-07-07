"""
FastAPI application — /search and /health endpoints.

POST /search  — symptom → NER → MedlinePlus → pgvector → BioMistral screen → ranked results
GET  /health  — liveness probe

Run: uvicorn serving.api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pipeline.search import SearchPipeline
from serving.cache import ResponseCache
from serving.guardrail import Guardrail

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


class ExperimentOut(BaseModel):
    name: str
    dataset: str
    start_time: str
    run_count: int | None = None
    scores: dict[str, float] = {}


class ExperimentsResponse(BaseModel):
    langsmith_configured: bool
    running: bool
    last_error: str | None = None
    experiments: list[ExperimentOut]


# ── App setup ─────────────────────────────────────────────────────────────────

_pipeline: SearchPipeline | None = None
_cache: ResponseCache | None = None
_guardrail: Guardrail | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _pipeline, _cache, _guardrail
    _pipeline = SearchPipeline()
    _cache = ResponseCache()
    _guardrail = Guardrail()
    logger.info("SearchPipeline, ResponseCache, and Guardrail initialized")
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
    assert _pipeline is not None and _cache is not None and _guardrail is not None

    verdict = await asyncio.to_thread(_guardrail.check, request.symptoms)
    if verdict.blocked:
        logger.warning("Blocked /search (%s, %s layer)", verdict.category, verdict.layer)
        raise HTTPException(status_code=400, detail="This request was blocked by the safety guardrail.")

    cached = _cache.get(request.symptoms, request.status_filter, request.max_results)
    if cached:
        logger.info("Cache hit for query: %.50s", request.symptoms)
        return SearchResponse(**cached)

    start = time.monotonic()
    try:
        pipeline_result = await _pipeline.run(
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


# ── Agentic RAG (LangGraph, streamed as SSE) ───────────────────────────────────

class AgentSearchRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    clarifications: str = Field(default="", max_length=2000)


_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from pipeline.agentic import AgenticRAG

        _agent = AgenticRAG()
    return _agent


@app.post("/agent/search")
async def agent_search(request: AgentSearchRequest) -> StreamingResponse:
    assert _guardrail is not None
    combined = f"{request.question}\n{request.clarifications}".strip()
    verdict = await asyncio.to_thread(_guardrail.check, combined)
    if verdict.blocked:
        logger.warning("Blocked /agent/search (%s, %s layer)", verdict.category, verdict.layer)
        raise HTTPException(status_code=400, detail="This request was blocked by the safety guardrail.")

    agent = _get_agent()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for event in agent.stream(request.question, request.clarifications):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("Agent stream failed")
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Agent pipeline failed'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # tell nginx not to buffer the stream
        },
    )


# ── Experiments (LangSmith eval monitoring) ────────────────────────────────────
# Uvicorn runs multiple workers, so the run/running state must live in Redis —
# an in-process lock would let each worker start its own experiment.

_EVAL_LOCK_KEY = "eval:running"
_EVAL_ERROR_KEY = "eval:last_error"
_EVAL_LOCK_TTL_S = 1800  # auto-expire so a crashed run can't wedge the button


def _eval_redis():
    import redis

    return redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))


class RunExperimentRequest(BaseModel):
    suite: str = Field(default="screener", pattern="^(screener|agent|guardrail)$")


def _run_eval(suite: str) -> None:
    r = _eval_redis()
    try:
        if suite == "agent":
            from eval.agent_harness import AgentEvalHarness

            metrics = AgentEvalHarness().run()
        elif suite == "guardrail":
            from eval.guardrail_harness import GuardrailEvalHarness

            metrics = GuardrailEvalHarness().run()
        else:
            from eval.harness import EvalHarness

            metrics = EvalHarness().run()
        logger.info("Eval experiment (%s) finished: %s", suite, metrics)
        r.delete(_EVAL_ERROR_KEY)
    except Exception as exc:
        logger.exception("Eval experiment failed")
        try:
            r.set(_EVAL_ERROR_KEY, str(exc), ex=86400)
        except Exception:
            pass
    finally:
        try:
            r.delete(_EVAL_LOCK_KEY)
        except Exception:
            pass


@app.post("/experiments/run", status_code=202)
async def run_experiment(request: RunExperimentRequest | None = None) -> dict:
    if not os.getenv("LANGCHAIN_API_KEY"):
        raise HTTPException(status_code=400, detail="LangSmith is not configured (LANGCHAIN_API_KEY missing)")
    suite = (request or RunExperimentRequest()).suite
    acquired = _eval_redis().set(_EVAL_LOCK_KEY, suite, nx=True, ex=_EVAL_LOCK_TTL_S)
    if not acquired:
        raise HTTPException(status_code=409, detail="An experiment is already running")
    threading.Thread(target=_run_eval, args=(suite,), daemon=True).start()
    return {"status": "started", "suite": suite}


@app.get("/experiments", response_model=ExperimentsResponse)
async def list_experiments() -> ExperimentsResponse:
    key = os.getenv("LANGCHAIN_API_KEY", "")
    if not key:
        return ExperimentsResponse(langsmith_configured=False, running=False, experiments=[])

    def _fetch() -> list[ExperimentOut]:
        from langsmith import Client

        from eval.agent_harness import DATASET_NAME as AGENT_DATASET
        from eval.guardrail_harness import DATASET_NAME as GUARDRAIL_DATASET
        from eval.harness import DATASET_NAME as SCREENER_DATASET

        client = Client(api_key=key)
        out: list[ExperimentOut] = []
        for dataset_name, label in [
            (SCREENER_DATASET, "screener"),
            (AGENT_DATASET, "agent"),
            (GUARDRAIL_DATASET, "guardrail"),
        ]:
            datasets = list(client.list_datasets(dataset_name=dataset_name))
            if not datasets:
                continue
            for project in client.list_projects(reference_dataset_id=datasets[0].id):
                # list_projects omits stats — fetch each project with include_stats
                try:
                    project = client.read_project(project_id=project.id, include_stats=True)
                except Exception:
                    logger.warning("Could not read stats for experiment %s", project.name)
                stats = getattr(project, "feedback_stats", None) or {}
                scores = {
                    k: round(v["avg"], 3)
                    for k, v in stats.items()
                    if isinstance(v, dict) and v.get("avg") is not None
                }
                out.append(
                    ExperimentOut(
                        name=project.name,
                        dataset=label,
                        start_time=project.start_time.isoformat() if project.start_time else "",
                        run_count=getattr(project, "run_count", None),
                        scores=scores,
                    )
                )
        out.sort(key=lambda e: e.start_time, reverse=True)
        return out[:25]

    try:
        experiments = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.exception("Failed to list experiments")
        raise HTTPException(status_code=502, detail="Could not reach LangSmith") from exc

    r = _eval_redis()
    try:
        running = bool(r.exists(_EVAL_LOCK_KEY))
        last_error_raw = r.get(_EVAL_ERROR_KEY)
        last_error = last_error_raw.decode() if last_error_raw else None
    except Exception:
        running, last_error = False, None

    return ExperimentsResponse(
        langsmith_configured=True,
        running=running,
        last_error=last_error,
        experiments=experiments,
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    cache_ok = _cache.ping() if _cache else False
    return HealthResponse(
        status="ok",
        model="BioMistral-7B-QLoRA",
        version="1.0.0",
        cache_ok=cache_ok,
    )
