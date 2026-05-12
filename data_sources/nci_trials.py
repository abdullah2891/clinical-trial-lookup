"""
NCI Cancer Trials API client.

Queries the NCI CTAPI (cancer.gov) for open cancer trials by disease keyword.
Normalizes results to the same Trial dataclass used by ClinicalTrialsGov.

Usage:
    client = NCITrials()
    trials = client.search("non-small cell lung cancer", max_results=10)
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .clinical_trials_gov import Trial

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
BASE_URL = "https://clinicaltrialsapi.cancer.gov/api/v2/trials"


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class NCITrials:
    """Client for the NCI Cancer Clinical Trials API v2."""

    def __init__(self) -> None:
        self._session = _build_session()

    def search(
        self,
        condition: str,
        max_results: int = 20,
        status_filter: str = "open",
    ) -> list[Trial]:
        """Return up to *max_results* NCI trials matching *condition*."""
        params: dict[str, Any] = {
            "diseases.name": condition,
            "current_trial_status": status_filter,
            "size": min(max_results, 50),
        }
        try:
            resp = self._session.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 401:
                logger.debug("NCI Trials API requires auth — skipping (no API key configured)")
                return []
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("NCI Trials fetch failed: %s", exc)
            return []

        trials: list[Trial] = []
        for item in data.get("data", []):
            try:
                trials.append(self._parse(item))
            except Exception as exc:
                logger.warning("Failed to parse NCI trial: %s", exc)
        return trials

    def _parse(self, item: dict[str, Any]) -> Trial:
        nct_id = item.get("nct_id", "")
        conditions = [d.get("name", "") for d in item.get("diseases", [])]
        interventions = [a.get("name", "") for a in item.get("arms", [])]
        locations = list(
            {
                site.get("org_city", "")
                for site in item.get("sites", [])
                if site.get("org_city")
            }
        )

        elig_parts: list[str] = []
        if inc := item.get("eligibility", {}).get("structured", {}).get("inclusion_indicator"):
            elig_parts.append(f"Inclusion: {inc}")
        if exc := item.get("eligibility", {}).get("structured", {}).get("exclusion_indicator"):
            elig_parts.append(f"Exclusion: {exc}")
        eligibility_summary = "\n".join(elig_parts) or item.get("detail_description", "")

        return Trial(
            nct_id=nct_id,
            title=item.get("brief_title", ""),
            status=item.get("current_trial_status", ""),
            conditions=conditions,
            interventions=interventions,
            eligibility_summary=eligibility_summary,
            sponsor=item.get("lead_org", ""),
            phase=item.get("phase", {}).get("phase", ""),
            start_date=item.get("start_date", ""),
            locations=locations,
            source="NCI Trials",
            url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        )
