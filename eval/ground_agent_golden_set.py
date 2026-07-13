"""
Verify the NCT grounding of eval/agent_golden_set.jsonl against a live pgvector
snapshot.

The golden set claims specific `expected_nct_ids` for each answerable question.
Those IDs are only useful as a target if they actually exist in the retrieval
corpus and are reachable by ANN search for that question. This script checks
both, so the golden set can't silently rot as the trial snapshot is refreshed.

For every non-adversarial record it:
  1. embeds the question and pulls the top-K nearest trials from pgvector
  2. reports which expected IDs are present in the DB at all
  3. reports which expected IDs are actually retrieved within top-K
  4. suggests high-similarity NCT IDs the question surfaces (candidates to add)

Adversarial records (expected_nct_ids == []) are reported for visibility but
never fail — their whole point is that nothing should match well.

Requires DATABASE_URL and OPENAI_API_KEY (same as the agent). Read-only.

Usage:
    python -m eval.ground_agent_golden_set
    python -m eval.ground_agent_golden_set --top-k 30 --suggest 5
    python -m eval.ground_agent_golden_set --category investor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("eval/agent_golden_set.jsonl")


def load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


async def _db_present(nct_ids: set[str]) -> set[str]:
    """Return which of nct_ids exist in the trial_embeddings table."""
    import os

    import asyncpg

    if not nct_ids:
        return set()
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        rows = await conn.fetch(
            "SELECT nct_id FROM trial_embeddings WHERE nct_id = ANY($1::text[])",
            list(nct_ids),
        )
    finally:
        await conn.close()
    return {r["nct_id"] for r in rows}


async def verify(path: Path, top_k: int, suggest: int, category: str | None) -> int:
    from etl.embedder import TrialEmbedder

    records = load_records(path)
    if category:
        records = [r for r in records if r.get("category") == category]

    all_expected: set[str] = set()
    for r in records:
        all_expected.update(r.get("expected_nct_ids", []))
    present = await _db_present(all_expected)

    embedder = TrialEmbedder()
    problems = 0
    total_answerable = 0

    for r in records:
        expected = set(r.get("expected_nct_ids", []))
        is_adversarial = r.get("category") == "adversarial" or not expected

        try:
            rows = await embedder.search_similar(r["question"], top_k=top_k)
        except Exception as exc:
            logger.error("[%s] retrieval failed: %s", r["id"], exc)
            problems += 1
            continue

        retrieved = {row["nct_id"] for row in rows}

        if is_adversarial:
            top_sim = rows[0].get("similarity", 0.0) if rows else 0.0
            print(f"{r['id']} [adversarial] top similarity={top_sim:.3f} (expected no strong match)")
            continue

        total_answerable += 1
        missing_from_db = expected - present
        hit = expected & retrieved

        status = "OK" if hit else "MISS"
        if not hit:
            problems += 1
        print(
            f"{r['id']} [{r.get('category','?')}] {status}: "
            f"{len(hit)}/{len(expected)} expected IDs retrieved in top-{top_k}"
        )
        if missing_from_db:
            print(f"    not in DB snapshot at all: {sorted(missing_from_db)}")
        not_retrieved = (expected & present) - retrieved
        if not_retrieved:
            print(f"    in DB but not retrieved for this phrasing: {sorted(not_retrieved)}")
        if not hit and suggest:
            top = [
                f"{row['nct_id']}({row.get('similarity', 0.0):.2f})"
                for row in rows[:suggest]
            ]
            print(f"    top candidates for this question: {top}")

    print("\n=== Grounding summary ===")
    print(f"  answerable questions checked: {total_answerable}")
    print(f"  expected IDs total (unique):  {len(all_expected)}")
    print(f"  present in DB snapshot:        {len(present)}/{len(all_expected)}")
    print(f"  questions with zero hits:      {problems}")
    return 1 if problems else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--suggest", type=int, default=3, help="Show N candidate IDs for misses")
    parser.add_argument("--category", default=None, help="Only verify one category")
    args = parser.parse_args()

    exit_code = asyncio.run(
        verify(Path(args.golden), args.top_k, args.suggest, args.category)
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
