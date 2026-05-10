"""
LangSmith eval harness for the clinical trial eligibility screener.

Runs the golden test set through the full pipeline, logs traces to LangSmith,
and prints a summary with accuracy, confidence calibration, and latency stats.

Usage:
    python eval/harness.py                        # run golden set
    python eval/harness.py --golden eval/golden_set.jsonl
    python eval/harness.py --n-samples 20         # quick smoke test
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import time
from pathlib import Path

from langsmith import Client as LangSmithClient
from langsmith.evaluation import evaluate as ls_evaluate

from models.screener import EligibilityScreener, ScreeningResult

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("eval/golden_set.jsonl")


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


def run_screener_on_example(example: dict, screener: EligibilityScreener) -> ScreeningResult:
    return screener.screen(
        patient_profile=example["patient"],
        eligibility_criteria=example["criteria"],
        nct_id=example.get("nct_id", ""),
        title=example.get("title", ""),
    )


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
        pred_eligible = pred.eligible
        is_correct = gt_eligible == pred_eligible

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


class EvalHarness:
    def __init__(self) -> None:
        self._screener = EligibilityScreener()
        ls_key = os.getenv("LANGCHAIN_API_KEY", "")
        self._ls_client = LangSmithClient(api_key=ls_key) if ls_key else None

    def run(self, golden_path: Path = GOLDEN_PATH, n_samples: int | None = None) -> dict:
        records = load_golden_set(golden_path, n=n_samples)
        logger.info("Running eval on %d examples", len(records))

        predictions: list[ScreeningResult] = []
        for i, record in enumerate(records):
            try:
                pred = run_screener_on_example(record, self._screener)
                predictions.append(pred)
            except Exception as exc:
                logger.warning("Example %d failed: %s", i, exc)
                predictions.append(
                    ScreeningResult(
                        nct_id=record.get("nct_id", ""),
                        title=record.get("title", ""),
                        eligible=False,
                        confidence=0.0,
                        reason=f"Error: {exc}",
                    )
                )

        metrics = compute_metrics(records, predictions)
        self._log_to_langsmith(records, predictions, metrics)
        return metrics

    def _log_to_langsmith(
        self,
        records: list[dict],
        predictions: list[ScreeningResult],
        metrics: dict,
    ) -> None:
        if not self._ls_client:
            return
        try:
            dataset_name = "clinical-trial-golden-set"
            # Upsert dataset
            datasets = list(self._ls_client.list_datasets(dataset_name=dataset_name))
            if datasets:
                dataset = datasets[0]
            else:
                dataset = self._ls_client.create_dataset(dataset_name=dataset_name)

            for record, pred in zip(records, predictions):
                self._ls_client.create_example(
                    inputs={"patient": record["patient"], "criteria": record["criteria"]},
                    outputs={
                        "eligible": pred.eligible,
                        "confidence": pred.confidence,
                        "reason": pred.reason,
                    },
                    dataset_id=dataset.id,
                )

            logger.info("Logged %d examples to LangSmith dataset: %s", len(records), dataset_name)
        except Exception as exc:
            logger.warning("LangSmith logging failed: %s", exc)


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
