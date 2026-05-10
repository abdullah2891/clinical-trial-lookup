"""
ClinicalTrials.gov v2 API client.

Fetches recruiting trials by condition keyword, normalizes to the shared
Trial dataclass. Uses a shared requests.Session with retries.

Usage:
    client = ClinicalTrialsGov()
    trials = client.search("type 2 diabetes", max_results=20)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


@dataclass
class Trial:
    nct_id: str
    title: str
    status: str
    conditions: list[str]
    interventions: list[str]
    eligibility_summary: str
    sponsor: str
    phase: str
    start_date: str
    locations: list[str]
    source: str
    url: str


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class ClinicalTrialsGov:
    """Client for the ClinicalTrials.gov v2 REST API."""

    def __init__(self) -> None:
        self._session = _build_session()

    def search(
        self,
        condition: str,
        max_results: int = 20,
        status_filter: str = "RECRUITING",
    ) -> list[Trial]:
        """Return up to *max_results* trials matching *condition*."""
        params: dict[str, Any] = {
            "query.cond": condition,
            "filter.overallStatus": status_filter,
            "pageSize": min(max_results, 100),
            "format": "json",
            "fields": (
                "NCTId,BriefTitle,OverallStatus,Condition,InterventionName,"
                "EligibilityCriteria,LeadSponsorName,Phase,StartDate,LocationCity"
            ),
        }
        try:
            resp = self._session.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("ClinicalTrials.gov fetch failed: %s", exc)
            return []

        trials: list[Trial] = []
        for study in data.get("studies", []):
            try:
                trials.append(self._parse(study))
            except Exception as exc:
                logger.warning("Failed to parse study: %s", exc)
        return trials

    def _parse(self, study: dict[str, Any]) -> Trial:
        ps = study.get("protocolSection", {})
        id_mod = ps.get("identificationModule", {})
        status_mod = ps.get("statusModule", {})
        cond_mod = ps.get("conditionsModule", {})
        arms_mod = ps.get("armsInterventionsModule", {})
        elig_mod = ps.get("eligibilityModule", {})
        sponsor_mod = ps.get("sponsorCollaboratorsModule", {})
        design_mod = ps.get("designModule", {})
        contacts_mod = ps.get("contactsLocationsModule", {})

        nct_id = id_mod.get("nctId", "")
        interventions = [
            i.get("interventionName", "")
            for i in arms_mod.get("interventions", [])
        ]
        locations = [
            loc.get("locationCity", "")
            for loc in contacts_mod.get("locations", [])
        ]

        return Trial(
            nct_id=nct_id,
            title=id_mod.get("briefTitle", ""),
            status=status_mod.get("overallStatus", ""),
            conditions=cond_mod.get("conditions", []),
            interventions=interventions,
            eligibility_summary=elig_mod.get("eligibilityCriteria", ""),
            sponsor=sponsor_mod.get("leadSponsor", {}).get("name", ""),
            phase=", ".join(design_mod.get("phases", [])),
            start_date=status_mod.get("startDateStruct", {}).get("date", ""),
            locations=locations,
            source="ClinicalTrials.gov",
            url=f"https://clinicaltrials.gov/study/{nct_id}",
        )
