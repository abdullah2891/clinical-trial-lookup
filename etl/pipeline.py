"""
Scheduled ETL pipeline — weekly trial ingestion into pgvector.

Designed to run as an Airflow DAG or AWS Batch job.
Fetches top conditions, retrieves trials, and upserts embeddings.

Usage:
    python -m etl.pipeline                    # one-shot run
    python -m etl.pipeline --conditions-file conditions.txt
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from data_sources import TrialAggregator
from etl.embedder import TrialEmbedder

logger = logging.getLogger(__name__)

DEFAULT_CONDITIONS = [
    "type 2 diabetes",
    "non-small cell lung cancer",
    "multiple sclerosis",
    "Crohn's disease",
    "major depressive disorder",
    "Alzheimer's disease",
    "breast cancer",
    "chronic kidney disease",
    "rheumatoid arthritis",
    "psoriasis",
    "atrial fibrillation",
    "heart failure",
    "COPD",
    "Parkinson's disease",
    "ovarian cancer",
]


async def run_ingestion(conditions: list[str], max_per_condition: int = 50) -> None:
    aggregator = TrialAggregator()
    embedder = TrialEmbedder()

    for condition in conditions:
        logger.info("Ingesting: %s", condition)
        try:
            trials = aggregator.search(condition, max_results=max_per_condition)
            if not trials:
                logger.warning("No trials found for: %s", condition)
                continue
            await embedder.embed_trials(trials)
            logger.info("Embedded %d trials for: %s", len(trials), condition)
        except Exception as exc:
            logger.warning("Failed to ingest %s: %s", condition, exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--conditions-file", default="")
    parser.add_argument("--max-per-condition", type=int, default=50)
    args = parser.parse_args()

    if args.conditions_file:
        conditions = Path(args.conditions_file).read_text().splitlines()
        conditions = [c.strip() for c in conditions if c.strip()]
    else:
        conditions = DEFAULT_CONDITIONS

    asyncio.run(run_ingestion(conditions, args.max_per_condition))


if __name__ == "__main__":
    main()
