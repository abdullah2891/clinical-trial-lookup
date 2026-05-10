"""
TrialAggregator — unified entry point for multi-source trial retrieval.

Fans out to ClinicalTrials.gov and NCI Trials in parallel, deduplicates
by NCT ID, and returns a single ranked list sorted by recency.

Usage:
    aggregator = TrialAggregator()
    trials = aggregator.search("type 2 diabetes", max_results=20)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .clinical_trials_gov import ClinicalTrialsGov, Trial
from .nci_trials import NCITrials

logger = logging.getLogger(__name__)


class TrialAggregator:
    """Aggregates trials from ClinicalTrials.gov and NCI Trials."""

    def __init__(self) -> None:
        self._ctgov = ClinicalTrialsGov()
        self._nci = NCITrials()

    def search(
        self,
        condition: str,
        max_results: int = 20,
        status_filter: str = "RECRUITING",
    ) -> list[Trial]:
        """
        Parallel fan-out to all sources; dedup by nct_id; return up to *max_results*.
        """
        nci_status = "open" if status_filter == "RECRUITING" else status_filter.lower()
        futures_map = {}

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures_map[pool.submit(
                self._ctgov.search, condition, max_results, status_filter
            )] = "ctgov"
            futures_map[pool.submit(
                self._nci.search, condition, max_results, nci_status
            )] = "nci"

            all_trials: list[Trial] = []
            for future in as_completed(futures_map):
                source = futures_map[future]
                try:
                    all_trials.extend(future.result())
                except Exception as exc:
                    logger.warning("Source %s raised: %s", source, exc)

        # Deduplicate by nct_id, preferring ClinicalTrials.gov entries
        seen: set[str] = set()
        deduped: list[Trial] = []
        for trial in all_trials:
            if trial.nct_id and trial.nct_id not in seen:
                seen.add(trial.nct_id)
                deduped.append(trial)

        return deduped[:max_results]
