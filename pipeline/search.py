"""
End-to-end search + screen pipeline.

Flow:
  symptom text
    → SciSpacy NER  (extract medical entities)
    → MedlinePlus   (normalize to canonical condition)
    → pgvector ANN  (top-20 semantically similar trials)
    → BioMistral-7B (screen each trial for eligibility)
    → ranked by confidence

Usage:
    pipeline = SearchPipeline()
    result = pipeline.run("chest tightness and shortness of breath", max_results=5)
"""

from __future__ import annotations

import asyncio
import logging
import os

from data_sources.medlineplus import MedlinePlus
from etl.embedder import TrialEmbedder
from etl.ontology import OntologyMapper
from models.screener import EligibilityScreener, ScreeningResult

logger = logging.getLogger(__name__)


class SearchPipeline:
    """Orchestrates the full symptom-to-ranked-trials pipeline."""

    def __init__(self) -> None:
        self._normalizer = MedlinePlus()
        self._ontology = OntologyMapper()
        self._embedder = TrialEmbedder()
        self._screener = EligibilityScreener()

    def run(
        self,
        symptoms: str,
        max_results: int = 5,
        status_filter: str = "RECRUITING",
    ) -> dict:
        """
        Synchronous entry point (wraps async retrieval).
        Returns: {normalized_condition, candidates_retrieved, results: [ScreeningResult]}
        """
        return asyncio.run(self._run_async(symptoms, max_results, status_filter))

    async def _run_async(
        self,
        symptoms: str,
        max_results: int,
        status_filter: str,
    ) -> dict:
        # Step 1: NER + normalization
        condition_names = self._ontology.extract_condition_names(symptoms)
        primary_condition = condition_names[0] if condition_names else symptoms
        normalized = self._normalizer.normalize(primary_condition)
        logger.info("Normalized '%s' → '%s'", symptoms[:80], normalized)

        # Step 2: pgvector ANN retrieval
        candidates = await self._embedder.search_similar(normalized, top_k=20)
        logger.info("Retrieved %d candidates from pgvector", len(candidates))

        if not candidates:
            return {
                "normalized_condition": normalized,
                "candidates_retrieved": 0,
                "results": [],
            }

        # Step 3: BioMistral eligibility screening
        trials_for_screening = [
            {
                "nct_id": c["nct_id"],
                "title": c["title"],
                "criteria": c["eligibility_summary"],
            }
            for c in candidates
        ]

        patient_profile = f"Patient symptoms: {symptoms}"
        screening_results = self._screener.screen_batch(patient_profile, trials_for_screening)

        # Step 4: Rank by confidence (eligible first, then by score)
        ranked = sorted(
            screening_results,
            key=lambda r: (not r.eligible, -r.confidence),
        )

        return {
            "normalized_condition": normalized,
            "candidates_retrieved": len(candidates),
            "results": ranked[:max_results],
        }


def search_and_screen(
    symptoms: str,
    max_results: int = 5,
    status_filter: str = "RECRUITING",
) -> dict:
    """Module-level convenience function matching CLAUDE.md reference."""
    return SearchPipeline().run(symptoms, max_results, status_filter)
