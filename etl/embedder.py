"""
Batch embedder — embeds all trials into pgvector for ANN retrieval.

Uses OpenAI text-embedding-3-large (1536-dim). Writes vectors to the
`trial_embeddings` table with an ivfflat cosine-similarity index.

Schema (auto-created if not present):
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE trial_embeddings (
        nct_id TEXT PRIMARY KEY,
        title TEXT,
        conditions TEXT[],
        eligibility_summary TEXT,
        embedding vector(1536),
        source TEXT,
        url TEXT,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

Usage:
    python -m etl.embedder --source ctgov --condition "diabetes"
    python -m etl.embedder --nct-ids NCT04280705 NCT03991065
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import asdict

import asyncpg
import numpy as np
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector

from data_sources import TrialAggregator
from data_sources.clinical_trials_gov import Trial

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536  # ivfflat max is 2000; use OpenAI's Matryoshka truncation
BATCH_SIZE = 32


def trial_to_text(trial: Trial) -> str:
    parts = [
        trial.title,
        "Conditions: " + ", ".join(trial.conditions),
        "Interventions: " + ", ".join(trial.interventions),
        trial.eligibility_summary[:1000],
    ]
    return "\n".join(p for p in parts if p)


class TrialEmbedder:
    """Embeds trials and upserts them into pgvector."""

    def __init__(self) -> None:
        self._openai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._db_url = os.environ["DATABASE_URL"]

    async def embed_trials(self, trials: list[Trial]) -> None:
        conn = await asyncpg.connect(self._db_url)
        # Extension must exist before register_vector queries its type OID
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        await self._ensure_schema(conn)

        texts = [trial_to_text(t) for t in trials]

        for batch_start in range(0, len(trials), BATCH_SIZE):
            batch = trials[batch_start : batch_start + BATCH_SIZE]
            batch_texts = texts[batch_start : batch_start + BATCH_SIZE]

            embeddings = await self._embed_batch(batch_texts)

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
            logger.info("Upserted batch %d-%d", batch_start, batch_start + len(batch))

        await self.rebuild_index(conn)
        total = await conn.fetchval("SELECT COUNT(*) FROM trial_embeddings")
        logger.info("Index rebuilt. Total rows: %d", total)
        await conn.close()

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        resp = await self._openai.embeddings.create(
            model=EMBEDDING_MODEL, input=texts, dimensions=EMBED_DIM
        )
        return [np.array(item.embedding, dtype=np.float32) for item in resp.data]

    async def search_similar(
        self, query: str, top_k: int = 20
    ) -> list[dict]:
        """ANN search: embed query → cosine nearest neighbours from pgvector."""
        resp = await self._openai.embeddings.create(
            model=EMBEDDING_MODEL, input=[query], dimensions=EMBED_DIM
        )
        query_vec = np.array(resp.data[0].embedding, dtype=np.float32)

        conn = await asyncpg.connect(self._db_url)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)

        rows = await conn.fetch(
            """
            SELECT nct_id, title, conditions, eligibility_summary, source, url,
                   1 - (embedding <=> $1) AS similarity
            FROM trial_embeddings
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            query_vec.tolist(),
            top_k,
        )
        await conn.close()

        return [dict(r) for r in rows]

    @staticmethod
    async def _ensure_schema(conn: asyncpg.Connection) -> None:
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

    @staticmethod
    async def rebuild_index(conn: asyncpg.Connection) -> None:
        """Build ivfflat index after data is loaded. lists = max(rows/50, 1)."""
        row_count = await conn.fetchval("SELECT COUNT(*) FROM trial_embeddings")
        if row_count == 0:
            return
        # ivfflat k-means needs ~6 bytes/vector/list; give it 2 GB headroom
        await conn.execute("SET maintenance_work_mem = '2GB'")
        lists = max(int(row_count / 50), 1)
        await conn.execute("DROP INDEX IF EXISTS trial_emb_idx")
        await conn.execute(f"""
            CREATE INDEX trial_emb_idx
            ON trial_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {lists})
        """)


async def _run_cli(args: argparse.Namespace) -> None:
    embedder = TrialEmbedder()

    if args.condition:
        aggregator = TrialAggregator()
        trials = aggregator.search(args.condition, max_results=100)
        logger.info("Fetched %d trials for condition: %s", len(trials), args.condition)
    else:
        logger.info("No condition specified — nothing to embed")
        return

    await embedder.embed_trials(trials)
    logger.info("Done embedding %d trials", len(trials))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", default="", help="Condition keyword to fetch and embed")
    parser.add_argument("--source", choices=["ctgov", "nci", "all"], default="all")
    args = parser.parse_args()
    asyncio.run(_run_cli(args))


if __name__ == "__main__":
    main()
