"""
Bulk downloader — pulls all ClinicalTrials.gov trials via the v2 JSON API.

Downloads trials in pages of 1000, embeds with text-embedding-3-large,
and upserts into pgvector. Far more comprehensive than per-condition search.

Stats (RECRUITING only):
  ~65 000 trials  ·  ~65 API pages  ·  ~$4 in embeddings  ·  ~10–15 min

Pagination uses the `nextPageToken` returned in each JSON response body.
Rate limits: 50 req/min (download) / ~3000 RPM (OpenAI embeddings).

Usage:
    # Full run — all recruiting trials
    python -m etl.bulk_downloader

    # Smoke test — first 5 pages (5 000 trials)
    python -m etl.bulk_downloader --max-pages 5

    # Different status
    python -m etl.bulk_downloader --status COMPLETED

    # Skip NCT IDs already in the database (safe to re-run)
    python -m etl.bulk_downloader --resume

    # Via docker compose
    docker compose run --rm etl python -m etl.bulk_downloader --max-pages 2
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Any

import asyncpg
import requests
from pgvector.asyncpg import register_vector
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data_sources.clinical_trials_gov import Trial
from etl.embedder import TrialEmbedder, trial_to_text

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 1000
EMBED_BATCH = 32           # trials per OpenAI embedding call
MIN_REQUEST_GAP = 1.2      # seconds between download pages (≤50 req/min)

# Fields requested from the API — keeps payload lean
FIELDS = ",".join([
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Condition",
    "InterventionName",
    "EligibilityCriteria",
    "LeadSponsorName",
    "Phase",
    "StartDate",
    "LocationCity",
    "BriefSummary",
])


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _parse_study(study: dict[str, Any]) -> Trial | None:
    """Parse a single v2 JSON study into our Trial dataclass."""
    try:
        ps = study.get("protocolSection", {})
        id_mod    = ps.get("identificationModule", {})
        status_mod = ps.get("statusModule", {})
        cond_mod  = ps.get("conditionsModule", {})
        arms_mod  = ps.get("armsInterventionsModule", {})
        elig_mod  = ps.get("eligibilityModule", {})
        sponsor_mod = ps.get("sponsorCollaboratorsModule", {})
        design_mod = ps.get("designModule", {})
        contacts_mod = ps.get("contactsLocationsModule", {})
        desc_mod  = ps.get("descriptionModule", {})

        nct_id = id_mod.get("nctId", "")
        if not nct_id:
            return None

        interventions = [
            i.get("name", "")
            for i in arms_mod.get("interventions", [])
        ]
        locations = list({
            loc.get("city", "")
            for loc in contacts_mod.get("locations", [])
            if loc.get("city")
        })

        # Combine eligibility criteria + brief summary for richer embeddings
        elig_text = elig_mod.get("eligibilityCriteria", "")
        brief = desc_mod.get("briefSummary", "")
        eligibility_summary = "\n\n".join(filter(None, [elig_text, brief]))

        return Trial(
            nct_id=nct_id,
            title=id_mod.get("briefTitle", ""),
            status=status_mod.get("overallStatus", ""),
            conditions=cond_mod.get("conditions", []),
            interventions=interventions,
            eligibility_summary=eligibility_summary[:3000],
            sponsor=sponsor_mod.get("leadSponsor", {}).get("name", ""),
            phase=", ".join(design_mod.get("phases", [])),
            start_date=status_mod.get("startDateStruct", {}).get("date", ""),
            locations=locations,
            source="ClinicalTrials.gov",
            url=f"https://clinicaltrials.gov/study/{nct_id}",
        )
    except Exception as exc:
        logger.debug("Parse error: %s", exc)
        return None


class BulkDownloader:
    """Pages through the CT.gov v2 API and streams trials into pgvector."""

    def __init__(self, status_filter: str = "RECRUITING", resume: bool = False) -> None:
        self._status = status_filter
        self._resume = resume
        self._session = _build_session()
        self._embedder = TrialEmbedder()

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, max_pages: int | None = None) -> None:
        conn = await asyncpg.connect(self._embedder._db_url)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        await self._ensure_table(conn)

        existing: set[str] = set()
        if self._resume:
            rows = await conn.fetch("SELECT nct_id FROM trial_embeddings")
            existing = {r["nct_id"] for r in rows}
            logger.info("Resume mode: %d trials already in DB", len(existing))

        total_upserted = 0
        page_num = 0
        page_token: str | None = None

        total_count = self._fetch_total_count()
        logger.info(
            "Starting bulk download: %d trials available (status=%s)",
            total_count, self._status,
        )

        while True:
            if max_pages and page_num >= max_pages:
                logger.info("Reached --max-pages %d, stopping.", max_pages)
                break

            t0 = time.monotonic()
            studies, next_token = self._fetch_page(page_token)

            if not studies:
                break

            trials = [t for s in studies if (t := _parse_study(s)) is not None]

            if self._resume:
                trials = [t for t in trials if t.nct_id not in existing]

            if trials:
                upserted = await self._embed_and_upsert(conn, trials)
                total_upserted += upserted

            page_num += 1
            pct = min(100, int(page_num * PAGE_SIZE * 100 / max(total_count, 1)))
            logger.info(
                "Page %d | parsed %d | upserted %d | total so far %d | ~%d%%",
                page_num, len(trials), upserted if trials else 0,
                total_upserted, pct,
            )

            page_token = next_token
            if not page_token:
                logger.info("No more pages — download complete.")
                break

            # Rate-limit: ≤ 50 req/min
            elapsed = time.monotonic() - t0
            if elapsed < MIN_REQUEST_GAP:
                await asyncio.sleep(MIN_REQUEST_GAP - elapsed)

        logger.info("Rebuilding ivfflat index on %d total rows...", total_upserted)
        await self._embedder.rebuild_index(conn)
        await conn.close()
        logger.info("Done. Total upserted this run: %d", total_upserted)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_total_count(self) -> int:
        try:
            params = {"pageSize": 1, "filter.overallStatus": self._status, "countTotal": "true"}
            resp = self._session.get(BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            return int(resp.json().get("totalCount", 0))
        except Exception as exc:
            logger.warning("Could not fetch total count: %s", exc)
            return 0

    def _fetch_page(self, page_token: str | None) -> tuple[list[dict], str | None]:
        params: dict[str, Any] = {
            "pageSize": PAGE_SIZE,
            "filter.overallStatus": self._status,
            "fields": FIELDS,
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token

        resp = self._session.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        return body.get("studies", []), body.get("nextPageToken")

    async def _embed_and_upsert(self, conn: asyncpg.Connection, trials: list[Trial]) -> int:
        upserted = 0
        for i in range(0, len(trials), EMBED_BATCH):
            batch = trials[i : i + EMBED_BATCH]
            texts = [trial_to_text(t) for t in batch]
            try:
                embeddings = await self._embedder.embed_batch(texts)
            except Exception as exc:
                logger.warning("Embedding batch %d failed: %s — skipping", i, exc)
                continue

            await conn.executemany(
                """
                INSERT INTO trial_embeddings
                    (nct_id, title, conditions, eligibility_summary, embedding, source, url)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (nct_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    conditions = EXCLUDED.conditions,
                    eligibility_summary = EXCLUDED.eligibility_summary,
                    embedding = EXCLUDED.embedding,
                    source = EXCLUDED.source,
                    url = EXCLUDED.url,
                    updated_at = now()
                """,
                [
                    (
                        t.nct_id,
                        t.title,
                        t.conditions,
                        t.eligibility_summary[:2000],
                        emb.tolist(),
                        t.source,
                        t.url,
                    )
                    for t, emb in zip(batch, embeddings)
                ],
            )
            upserted += len(batch)
        return upserted

    @staticmethod
    async def _ensure_table(conn: asyncpg.Connection) -> None:
        from etl.embedder import EMBED_DIM
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS trial_embeddings (
                nct_id TEXT PRIMARY KEY,
                title TEXT,
                conditions TEXT[],
                eligibility_summary TEXT,
                embedding vector({EMBED_DIM}),
                source TEXT,
                url TEXT,
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """)


async def _main(args: argparse.Namespace) -> None:
    downloader = BulkDownloader(
        status_filter=args.status,
        resume=args.resume,
    )
    await downloader.run(max_pages=args.max_pages)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Bulk download ClinicalTrials.gov → pgvector")
    parser.add_argument(
        "--status", default="RECRUITING",
        help="Trial status filter (default: RECRUITING). Use ALL for no filter.",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Stop after this many pages (1 page = 1000 trials). Omit for full run.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip NCT IDs already present in the database.",
    )
    args = parser.parse_args()
    if args.status == "ALL":
        args.status = ""
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
