"""
Eval harness for the LangGraph agentic RAG pipeline.

Runs eval/agent_golden_set.jsonl (questions grounded in real NCT IDs verified
present in the pgvector snapshot) through AgenticRAG and scores:

  - citation_recall       cited trials hit at least one expected NCT ID
                          (for adversarial no-answer cases: cited nothing)
  - citation_faithfulness every cited NCT ID was actually retrieved — i.e.
                          the agent never hallucinates trial IDs
  - answer_quality        gpt-4o-mini judge scores the answer 0-1 against
                          reference notes

With LANGCHAIN_API_KEY set, uploads the dataset once (idempotent) and records
each run as a LangSmith experiment. Offline otherwise.

Usage:
    python -m eval.agent_harness
    python -m eval.agent_harness --n-samples 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import time
from pathlib import Path

from langsmith import Client as LangSmithClient
from langsmith.evaluation import evaluate as ls_evaluate

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("eval/agent_golden_set.jsonl")
DATASET_NAME = "clinical-agentic-golden-set"

JUDGE_PROMPT = """You are grading an AI research assistant's answer about clinical trials.

Question: {question}

Reference notes describing a good answer:
{reference_notes}

Assistant's answer:
{answer}

Trials the assistant cited: {cited}

Score the answer from 0.0 to 1.0 for relevance, correctness against the reference
notes, and honesty (admitting when nothing relevant was found is good; forcing
irrelevant citations is bad).

Respond with ONLY a JSON object: {{"score": 0.0-1.0, "reasoning": "one sentence"}}"""


def load_golden_set(path: Path, n: int | None = None) -> list[dict]:
    records = [json.loads(line) for line in path.open() if line.strip()]
    return records[:n] if n else records


def _run_agent(question: str) -> dict:
    """Fresh agent per call — async clients don't survive event-loop reuse."""
    from pipeline.agentic import AgenticRAG

    start = time.monotonic()
    result = asyncio.run(AgenticRAG().run(question))
    result["latency_ms"] = (time.monotonic() - start) * 1000
    return result


# ── Evaluators ──────────────────────────────────────────────────────────────────

def citation_recall(run, example) -> dict:
    expected = set(example.outputs.get("expected_nct_ids", []))
    cited = set(run.outputs.get("relevant_nct_ids", []))
    if not expected:  # adversarial: nothing relevant exists
        score = 1.0 if not cited else 0.0
    else:
        score = 1.0 if cited & expected else 0.0
    return {"key": "citation_recall", "score": score}


def citation_faithfulness(run, example) -> dict:
    cited = set(run.outputs.get("relevant_nct_ids", []))
    retrieved = set(run.outputs.get("retrieved_nct_ids", []))
    return {"key": "citation_faithfulness", "score": 1.0 if cited <= retrieved else 0.0}


def answer_quality(run, example) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    prompt = JUDGE_PROMPT.format(
        question=example.inputs["question"],
        reference_notes=example.outputs.get("reference_notes", ""),
        answer=run.outputs.get("answer", ""),
        cited=json.dumps(run.outputs.get("relevant_nct_ids", [])),
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.0,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        return {
            "key": "answer_quality",
            "score": max(0.0, min(1.0, float(raw.get("score", 0.0)))),
            "comment": str(raw.get("reasoning", "")),
        }
    except Exception as exc:
        logger.warning("Judge failed: %s", exc)
        return {"key": "answer_quality", "score": 0.0, "comment": f"judge error: {exc}"}


def _score_offline(records: list[dict], outputs: list[dict]) -> dict:
    """Compute the same metrics locally without LangSmith objects."""

    class _Shim:
        def __init__(self, inputs=None, outputs=None):
            self.inputs = inputs or {}
            self.outputs = outputs or {}

    recalls, faiths, quals = [], [], []
    for rec, out in zip(records, outputs):
        run = _Shim(outputs=out)
        example = _Shim(
            inputs={"question": rec["question"]},
            outputs={"expected_nct_ids": rec["expected_nct_ids"], "reference_notes": rec["reference_notes"]},
        )
        recalls.append(citation_recall(run, example)["score"])
        faiths.append(citation_faithfulness(run, example)["score"])
        quals.append(answer_quality(run, example)["score"])
    return {
        "citation_recall": statistics.mean(recalls),
        "citation_faithfulness": statistics.mean(faiths),
        "answer_quality": statistics.mean(quals),
        "mean_iterations": statistics.mean(o.get("iterations", 0) for o in outputs),
        "mean_latency_ms": statistics.mean(o.get("latency_ms", 0.0) for o in outputs),
        "n_evaluated": len(records),
    }


class AgentEvalHarness:
    def __init__(self) -> None:
        ls_key = os.getenv("LANGCHAIN_API_KEY", "")
        self._ls_client = LangSmithClient(api_key=ls_key) if ls_key else None

    def run(self, golden_path: Path = GOLDEN_PATH, n_samples: int | None = None) -> dict:
        records = load_golden_set(golden_path, n=n_samples)
        logger.info("Running agent eval on %d questions", len(records))
        if self._ls_client:
            return self._run_langsmith(records)
        logger.info("LANGCHAIN_API_KEY not set — running offline")
        outputs = [_run_agent(r["question"]) for r in records]
        return _score_offline(records, outputs)

    def _ensure_dataset(self, records: list[dict]) -> None:
        if list(self._ls_client.list_datasets(dataset_name=DATASET_NAME)):
            return
        dataset = self._ls_client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Grounded golden questions for the LangGraph agentic RAG (expected NCT IDs verified in the pgvector snapshot)",
        )
        for record in records:
            self._ls_client.create_example(
                inputs={"question": record["question"]},
                outputs={
                    "expected_nct_ids": record["expected_nct_ids"],
                    "reference_notes": record["reference_notes"],
                },
                metadata={"id": record["id"]},
                dataset_id=dataset.id,
            )
        logger.info("Created LangSmith dataset '%s' (%d examples)", DATASET_NAME, len(records))

    def _run_langsmith(self, records: list[dict]) -> dict:
        self._ensure_dataset(records)
        collected: dict[str, dict] = {}

        def target(inputs: dict) -> dict:
            out = _run_agent(inputs["question"])
            collected[inputs["question"]] = out
            return out

        experiment = ls_evaluate(
            target,
            data=DATASET_NAME,
            evaluators=[citation_recall, citation_faithfulness, answer_quality],
            experiment_prefix="agentic-rag",
            client=self._ls_client,
            max_concurrency=2,
        )
        ordered = [collected.get(r["question"], {}) for r in records]
        metrics = _score_offline(records, ordered)
        metrics["experiment"] = getattr(experiment, "experiment_name", "")
        return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--n-samples", type=int, default=None)
    args = parser.parse_args()

    metrics = AgentEvalHarness().run(Path(args.golden), n_samples=args.n_samples)

    print("\n=== Agentic RAG Eval ===")
    for k, v in metrics.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")


if __name__ == "__main__":
    main()
