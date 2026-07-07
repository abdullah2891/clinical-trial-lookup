"""
Eval harness for the input guardrail.

Runs eval/guardrail_golden_set.jsonl (malicious inputs across 5 attack
categories + benign and hard-benign negatives) through Guardrail.check and
scores it as a binary classifier where "block" is the positive class:

  - block_recall      fraction of malicious inputs correctly blocked
                      (catch rate — the security metric that matters most)
  - benign_pass_rate  fraction of legitimate inputs correctly allowed
                      (1 - false-positive rate; guards against over-blocking
                      patients who mention overdose/suicidal ideation)
  - accuracy          overall correct decisions

With LANGCHAIN_API_KEY set, uploads the dataset once and records a LangSmith
experiment. Offline otherwise.

Usage:
    python -m eval.guardrail_harness
    python -m eval.guardrail_harness --n-samples 5
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

from serving.guardrail import Guardrail

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("eval/guardrail_golden_set.jsonl")
DATASET_NAME = "clinical-guardrail-golden-set"


def load_golden_set(path: Path, n: int | None = None) -> list[dict]:
    records = [json.loads(line) for line in path.open() if line.strip()]
    return records[:n] if n else records


def _decide(guardrail: Guardrail, text: str) -> dict:
    verdict = guardrail.check(text)
    return {
        "decision": "block" if verdict.blocked else "allow",
        "category": verdict.category,
        "layer": verdict.layer,
        "reason": verdict.reason,
    }


# ── Evaluators (positive class = "block") ──────────────────────────────────────

def decision_correct(run, example) -> dict:
    return {
        "key": "decision_correct",
        "score": int(run.outputs["decision"] == example.outputs["expected"]),
    }


def caught_attack(run, example) -> dict:
    """Only scored on malicious examples: did we block it?"""
    if example.outputs["expected"] != "block":
        return {"key": "caught_attack", "score": None}
    return {"key": "caught_attack", "score": int(run.outputs["decision"] == "block")}


def preserved_benign(run, example) -> dict:
    """Only scored on benign examples: did we allow it (no false positive)?"""
    if example.outputs["expected"] != "allow":
        return {"key": "preserved_benign", "score": None}
    return {"key": "preserved_benign", "score": int(run.outputs["decision"] == "allow")}


def _score_offline(records: list[dict], outputs: list[dict]) -> dict:
    correct, blocks_hit, blocks_total, allows_hit, allows_total = 0, 0, 0, 0, 0
    confusion: list[dict] = []
    for rec, out in zip(records, outputs):
        expected = rec["expected"]
        got = out["decision"]
        if got == expected:
            correct += 1
        else:
            confusion.append({"id": rec["id"], "category": rec["category"], "expected": expected, "got": got})
        if expected == "block":
            blocks_total += 1
            blocks_hit += int(got == "block")
        else:
            allows_total += 1
            allows_hit += int(got == "allow")
    return {
        "accuracy": correct / len(records) if records else 0.0,
        "block_recall": blocks_hit / blocks_total if blocks_total else 0.0,
        "benign_pass_rate": allows_hit / allows_total if allows_total else 0.0,
        "n_evaluated": len(records),
        "misclassified": confusion,
    }


class GuardrailEvalHarness:
    def __init__(self) -> None:
        self._guardrail = Guardrail()
        ls_key = os.getenv("LANGCHAIN_API_KEY", "")
        self._ls_client = LangSmithClient(api_key=ls_key) if ls_key else None

    def run(self, golden_path: Path = GOLDEN_PATH, n_samples: int | None = None) -> dict:
        records = load_golden_set(golden_path, n=n_samples)
        logger.info("Running guardrail eval on %d inputs", len(records))
        if self._ls_client:
            return self._run_langsmith(records)
        logger.info("LANGCHAIN_API_KEY not set — running offline")
        outputs = [_decide(self._guardrail, r["input"]) for r in records]
        return _score_offline(records, outputs)

    def _ensure_dataset(self, records: list[dict]) -> None:
        if list(self._ls_client.list_datasets(dataset_name=DATASET_NAME)):
            return
        dataset = self._ls_client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Malicious-intent inputs (5 attack categories) + benign/hard-benign negatives for the input guardrail",
        )
        for record in records:
            self._ls_client.create_example(
                inputs={"input": record["input"]},
                outputs={"expected": record["expected"], "category": record["category"]},
                metadata={"id": record["id"]},
                dataset_id=dataset.id,
            )
        logger.info("Created LangSmith dataset '%s' (%d examples)", DATASET_NAME, len(records))

    def _run_langsmith(self, records: list[dict]) -> dict:
        self._ensure_dataset(records)
        collected: dict[str, dict] = {}

        def target(inputs: dict) -> dict:
            out = _decide(self._guardrail, inputs["input"])
            collected[inputs["input"]] = out
            return out

        experiment = ls_evaluate(
            target,
            data=DATASET_NAME,
            evaluators=[decision_correct, caught_attack, preserved_benign],
            experiment_prefix="guardrail",
            client=self._ls_client,
            max_concurrency=4,
        )
        ordered = [collected.get(r["input"], {"decision": "allow"}) for r in records]
        metrics = _score_offline(records, ordered)
        metrics["experiment"] = getattr(experiment, "experiment_name", "")
        return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--n-samples", type=int, default=None)
    args = parser.parse_args()

    metrics = GuardrailEvalHarness().run(Path(args.golden), n_samples=args.n_samples)

    print("\n=== Guardrail Eval ===")
    for k, v in metrics.items():
        if k == "misclassified":
            if v:
                print("  misclassified:")
                for m in v:
                    print(f"    {m['id']} ({m['category']}): expected {m['expected']}, got {m['got']}")
            continue
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")


if __name__ == "__main__":
    main()
