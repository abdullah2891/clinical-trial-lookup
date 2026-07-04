"""
LangSmith eval harness for the clinical trial eligibility screener.

Runs the golden test set through the screener. With LANGCHAIN_API_KEY set,
uploads the golden set as a LangSmith dataset (ground-truth labels as outputs,
created once — idempotent) and records each run as a LangSmith experiment with
per-example feedback scores. Without a key, runs fully offline.

Either way, prints accuracy, confidence calibration, and latency stats.

Dependencies: langsmith, models.screener (which needs OPENAI_API_KEY or a
Modal endpoint).

Usage:
    python -m eval.harness                        # full golden set
    python -m eval.harness --n-samples 3          # quick smoke test
    python -m eval.harness --golden eval/golden_set.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
from pathlib import Path

from langsmith import Client as LangSmithClient
from langsmith.evaluation import evaluate as ls_evaluate

from models.screener import EligibilityScreener, ScreeningResult

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("eval/golden_set.jsonl")
DATASET_NAME = "clinical-trial-golden-set"


def load_golden_set(path: Path, n: int | None = None) -> list[dict]:
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if n:
        records = records[:n]
    return records


def compute_metrics(
    records: list[dict],
    predictions: list[ScreeningResult],
) -> dict:
    correct = 0
    confident_correct = 0
    confident_total = 0
    latencies: list[float] = []
    confidences: list[float] = []

    for record, pred in zip(records, predictions):
        gt_eligible = bool(record["label"]["eligible"])
        is_correct = gt_eligible == pred.eligible

        if is_correct:
            correct += 1
        if pred.confidence >= 0.8:
            confident_total += 1
            if is_correct:
                confident_correct += 1

        latencies.append(pred.latency_ms)
        confidences.append(pred.confidence)

    n = len(records)
    return {
        "accuracy": correct / n if n else 0.0,
        "high_confidence_precision": confident_correct / confident_total if confident_total else 0.0,
        "high_confidence_rate": confident_total / n if n else 0.0,
        "mean_confidence": statistics.mean(confidences) if confidences else 0.0,
        "mean_latency_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0,
        "n_evaluated": n,
    }


# ── LangSmith evaluators (run once per example, scores shown in the UI) ────────

def eligibility_correct(run, example) -> dict:
    """1 if the predicted eligible/ineligible verdict matches ground truth."""
    return {
        "key": "eligibility_correct",
        "score": int(run.outputs["eligible"] == example.outputs["eligible"]),
    }


def confidence_abs_error(run, example) -> dict:
    """Absolute gap between predicted and reference confidence (lower = better)."""
    return {
        "key": "confidence_abs_error",
        "score": abs(run.outputs["confidence"] - example.outputs["confidence"]),
    }


class EvalHarness:
    def __init__(self) -> None:
        self._screener = EligibilityScreener()
        ls_key = os.getenv("LANGCHAIN_API_KEY", "")
        self._ls_client = LangSmithClient(api_key=ls_key) if ls_key else None

    def run(self, golden_path: Path = GOLDEN_PATH, n_samples: int | None = None) -> dict:
        records = load_golden_set(golden_path, n=n_samples)
        logger.info("Running eval on %d examples", len(records))

        if self._ls_client:
            return self._run_langsmith(records)
        logger.info("LANGCHAIN_API_KEY not set — running offline")
        return self._run_offline(records)

    # ── Offline path ───────────────────────────────────────────────────────────

    def _screen_record(self, record: dict) -> ScreeningResult:
        try:
            return self._screener.screen(
                patient_profile=record["patient"],
                eligibility_criteria=record["criteria"],
                nct_id=record.get("nct_id", ""),
                title=record.get("title", ""),
            )
        except Exception as exc:
            logger.warning("Screening failed for %s: %s", record.get("nct_id"), exc)
            return ScreeningResult(
                nct_id=record.get("nct_id", ""),
                title=record.get("title", ""),
                eligible=False,
                confidence=0.0,
                reason=f"Error: {exc}",
            )

    def _run_offline(self, records: list[dict]) -> dict:
        predictions = [self._screen_record(r) for r in records]
        return compute_metrics(records, predictions)

    # ── LangSmith path ─────────────────────────────────────────────────────────

    def _ensure_dataset(self, records: list[dict]) -> None:
        """Create the golden dataset once; never duplicate examples on re-runs."""
        existing = list(self._ls_client.list_datasets(dataset_name=DATASET_NAME))
        if existing:
            return
        dataset = self._ls_client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Adversarial golden set for trial eligibility screening",
        )
        for record in records:
            self._ls_client.create_example(
                inputs={"patient": record["patient"], "criteria": record["criteria"]},
                outputs=record["label"],  # ground truth, not predictions
                metadata={"nct_id": record.get("nct_id", "")},
                dataset_id=dataset.id,
            )
        logger.info("Created LangSmith dataset '%s' (%d examples)", DATASET_NAME, len(records))

    def _run_langsmith(self, records: list[dict]) -> dict:
        self._ensure_dataset(records)

        # evaluate() may run examples in any order — key predictions by input
        predictions: dict[str, ScreeningResult] = {}

        def target(inputs: dict) -> dict:
            result = self._screener.screen(
                patient_profile=inputs["patient"],
                eligibility_criteria=inputs["criteria"],
            )
            predictions[inputs["patient"]] = result
            return {
                "eligible": result.eligible,
                "confidence": result.confidence,
                "reason": result.reason,
            }

        experiment = ls_evaluate(
            target,
            data=DATASET_NAME,
            evaluators=[eligibility_correct, confidence_abs_error],
            experiment_prefix="eligibility-screener",
            client=self._ls_client,
        )

        ordered = [
            predictions.get(r["patient"])
            or ScreeningResult(nct_id=r.get("nct_id", ""), title="", eligible=False,
                               confidence=0.0, reason="missing prediction")
            for r in records
        ]
        metrics = compute_metrics(records, ordered)
        metrics["experiment"] = getattr(experiment, "experiment_name", "")
        return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--n-samples", type=int, default=None)
    args = parser.parse_args()

    harness = EvalHarness()
    metrics = harness.run(Path(args.golden), n_samples=args.n_samples)

    print("\n=== Eval Results ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.3f}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
