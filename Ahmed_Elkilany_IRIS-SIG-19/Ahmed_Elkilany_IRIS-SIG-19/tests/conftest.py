import os
from datetime import date
from pathlib import Path

import pytest

from gazette_harvester.geo import Gazetteer, GeoResolver
from gazette_harvester.http import FixtureFetcher
from gazette_harvester.repository import UpsertCounts

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "tests" / "fixtures" / "site"
EDGE = ROOT / "tests" / "fixtures" / "edge"
TODAY = date(2026, 10, 27)
BASE = "https://www.nussbaum.de/kiosk/mitteilungsblaetter"
INDEX = BASE


@pytest.fixture
def resolver():
    gaz, problems = Gazetteer.from_csv(ROOT / "data" / "gazetteer_sample.csv")
    assert problems == []
    return GeoResolver(gaz)


@pytest.fixture
def site_fetcher():
    return FixtureFetcher(SITE)


class FakeRepo:
    """In-memory stand-in with the same insert/update/unchanged accounting as the SQL upsert."""

    def __init__(self, fail_with=None):
        self.store = {}
        self.fail_with = fail_with

    def upsert_many(self, rows):
        if self.fail_with:
            raise self.fail_with
        c = UpsertCounts()
        for r in rows:
            key = (r.source_id, r.external_id)
            if key not in self.store:
                c.inserted += 1
            elif self.store[key].content_hash != r.content_hash:
                c.updated += 1
            else:
                c.unchanged += 1
                continue
            self.store[key] = r
        return c


@pytest.fixture
def fake_repo():
    return FakeRepo()


@pytest.fixture
def pg_dsn():
    dsn = os.environ.get("IRIS_TEST_DSN")
    if not dsn:
        pytest.skip("IRIS_TEST_DSN not set (needs PostgreSQL 16 + PostGIS)")
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS iris_staging CASCADE")
    from gazette_harvester.repository import PostgresRepository

    PostgresRepository(dsn).init_schema()
    return dsn
