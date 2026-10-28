from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .models import StagingRow

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

UPSERT = """
INSERT INTO iris_staging.signal_ingest (
    source_id, signal_type, external_id, title, published_on, source_url, publication_slug,
    issue_no, issue_year, municipality_name, municipality_ags, region, geom, geo_status, geo_note,
    access_level, quality_flags, content_hash, raw, harvest_run_id
) VALUES (
    %(source_id)s, %(signal_type)s, %(external_id)s, %(title)s, %(published_on)s, %(source_url)s,
    %(publication_slug)s, %(issue_no)s, %(issue_year)s, %(municipality_name)s, %(municipality_ags)s,
    %(region)s,
    CASE WHEN %(x)s::double precision IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(x)s::double precision, %(y)s::double precision), 25832) END,
    %(geo_status)s, %(geo_note)s, %(access_level)s, %(quality_flags)s, %(content_hash)s,
    %(raw)s, %(harvest_run_id)s
)
ON CONFLICT (source_id, external_id) DO UPDATE SET
    title = EXCLUDED.title,
    published_on = EXCLUDED.published_on,
    source_url = EXCLUDED.source_url,
    municipality_ags = EXCLUDED.municipality_ags,
    geom = EXCLUDED.geom,
    geo_status = EXCLUDED.geo_status,
    geo_note = EXCLUDED.geo_note,
    access_level = EXCLUDED.access_level,
    quality_flags = EXCLUDED.quality_flags,
    content_hash = EXCLUDED.content_hash,
    raw = EXCLUDED.raw,
    harvest_run_id = EXCLUDED.harvest_run_id,
    updated_at = now()
WHERE iris_staging.signal_ingest.content_hash IS DISTINCT FROM EXCLUDED.content_hash
RETURNING (xmax = 0) AS inserted
"""


@dataclass
class UpsertCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    def add(self, other: "UpsertCounts") -> None:
        self.inserted += other.inserted
        self.updated += other.updated
        self.unchanged += other.unchanged


def _params(row: StagingRow) -> dict:
    return {
        "source_id": row.source_id,
        "signal_type": row.signal_type,
        "external_id": row.external_id,
        "title": row.title,
        "published_on": row.published_on,
        "source_url": row.source_url,
        "publication_slug": row.publication_slug,
        "issue_no": row.issue_no,
        "issue_year": row.issue_year,
        "municipality_name": row.municipality_name,
        "municipality_ags": row.municipality_ags,
        "region": row.region,
        "x": row.x,
        "y": row.y,
        "geo_status": row.geo_status,
        "geo_note": row.geo_note,
        "access_level": row.access_level,
        "quality_flags": row.quality_flags,
        "content_hash": row.content_hash,
        "raw": Jsonb(row.raw),
        "harvest_run_id": row.harvest_run_id,
    }


class PostgresRepository:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def init_schema(self) -> None:
        ddl = (SQL_DIR / "001_signal_ingest.sql").read_text(encoding="utf-8")
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(ddl)

    def upsert_many(self, rows: list[StagingRow]) -> UpsertCounts:
        """All rows go in one transaction, so a publication is either fully loaded or not at all."""
        counts = UpsertCounts()
        if not rows:
            return counts
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(UPSERT, _params(row))
                    res = cur.fetchone()
                    if res is None:
                        counts.unchanged += 1
                    elif res[0]:
                        counts.inserted += 1
                    else:
                        counts.updated += 1
            conn.commit()
        return counts


class DryRunRepository:
    """Used with --dry-run: nothing is written, rows are only counted."""

    def __init__(self):
        self.rows: list[StagingRow] = []

    def upsert_many(self, rows: list[StagingRow]) -> UpsertCounts:
        self.rows.extend(rows)
        return UpsertCounts(inserted=len(rows))
