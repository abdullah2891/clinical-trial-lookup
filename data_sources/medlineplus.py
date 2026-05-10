"""
MedlinePlus NLM symptom normalizer.

Converts free-text symptom descriptions into canonical medical condition names
using the MedlinePlus Connect web service (no auth required).

Usage:
    normalizer = MedlinePlus()
    condition = normalizer.normalize("chest tightness and shortness of breath")
    # → "Dyspnea"
"""

from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
BASE_URL = "https://connect.medlineplus.gov/service"


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class MedlinePlus:
    """Normalizes symptom text to canonical condition names via MedlinePlus Connect."""

    def __init__(self) -> None:
        self._session = _build_session()

    def normalize(self, symptom_text: str) -> str:
        """
        Return the best-matching canonical condition name for *symptom_text*.
        Falls back to the original text if the API returns nothing useful.
        """
        params = {
            "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.90",  # ICD-10
            "mainSearchCriteria.v.dn": symptom_text,
            "knowledgeResponseType": "application/json",
            "informationRecipient": "PAT",
        }
        try:
            resp = self._session.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("MedlinePlus normalize failed: %s", exc)
            return symptom_text

        try:
            feed = data.get("feed", {})
            entries = feed.get("entry", [])
            if entries:
                title = entries[0].get("title", {})
                if isinstance(title, dict):
                    return title.get("_value", symptom_text)
                return str(title) or symptom_text
        except Exception as exc:
            logger.warning("MedlinePlus parse error: %s", exc)

        return symptom_text

    def normalize_batch(self, symptom_texts: list[str]) -> list[str]:
        """Normalize a list of symptom descriptions."""
        return [self.normalize(t) for t in symptom_texts]
