"""Integration tests against a real PostgreSQL 16 + PostGIS 3.4.

Run with:  IRIS_TEST_DSN=postgresql://user:pw@localhost:5432/dbname pytest -m pg
They drop and recreate the iris_staging schema, so point them at a scratch database.
"""
import dataclasses
from datetime import date

import psycopg
import pytest

from conftest import INDEX, SITE, TODAY
from gazette_harvester.http import FixtureFetcher
from gazette_harvester.pipeline import run_harvest
from gazette_harvester.repository import PostgresRepository, SQL_DIR
from test_normalize import issue
from gazette_harvester.normalize import build_rows

pytestmark = pytest.mark.pg


def query(dsn, sql, *args):
    with psycopg.connect(dsn) as conn:
        return conn.execute(sql, args).fetchall()


def harvest(dsn, resolver, run_id):
    return run_harvest(fetcher=FixtureFetcher(SITE), repo=PostgresRepository(dsn), resolver=resolver,
                       run_id=run_id, index_url=INDEX, today=TODAY)


def test_init_schema_is_repeatable(pg_dsn):
    repo = PostgresRepository(pg_dsn)
    repo.init_schema()
    repo.init_schema()
    assert query(pg_dsn, "select count(*) from iris_staging.signal_ingest") == [(0,)]


def test_rerun_is_idempotent_in_the_database(pg_dsn, resolver):
    first = harvest(pg_dsn, resolver, "run-1")
    assert first.counters["rows_inserted"] == 75
    second = harvest(pg_dsn, resolver, "run-2")
    assert (second.counters["rows_inserted"], second.counters["rows_updated"], second.counters["rows_unchanged"]) == (0, 0, 75)
    assert query(pg_dsn, "select count(*), count(distinct (source_id, external_id)) from iris_staging.signal_ingest") == [(75, 75)]
    # rows untouched by the second run still say which run wrote them
    assert query(pg_dsn, "select distinct harvest_run_id from iris_staging.signal_ingest") == [("run-1",)]


def test_points_are_stored_as_epsg25832(pg_dsn, resolver):
    harvest(pg_dsn, resolver, "run-1")
    srid, gtype, x, y = query(
        pg_dsn,
        "select ST_SRID(geom), GeometryType(geom), ST_X(geom), ST_Y(geom) from iris_staging.signal_ingest "
        "where municipality_name = 'Bammental' limit 1")[0]
    assert (srid, gtype) == (25832, "POINT")
    lon, lat = query(pg_dsn, "select ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326)) "
                             "from iris_staging.signal_ingest where municipality_name = 'Bammental' limit 1")[0]
    assert (round(lon, 4), round(lat, 4)) == (8.7758, 49.3508)


def test_changed_content_updates_in_place(pg_dsn, resolver):
    repo = PostgresRepository(pg_dsn)
    rows, _ = build_rows(issue(), resolver, "run-1")
    assert repo.upsert_many(rows).inserted == 3
    changed, _ = build_rows(issue(published_on=date(2026, 10, 22)), resolver, "run-2")
    counts = repo.upsert_many(changed)
    assert (counts.inserted, counts.updated, counts.unchanged) == (0, 3, 0)
    day, run_id, newer = query(pg_dsn, "select published_on, harvest_run_id, updated_at > ingested_at "
                                       "from iris_staging.signal_ingest limit 1")[0]
    assert (str(day), run_id, newer) == ("2026-10-22", "run-2", True)


def test_database_refuses_resolved_rows_without_a_point(pg_dsn, resolver):
    rows, _ = build_rows(issue(), resolver, "r")
    bad = dataclasses.replace(rows[0], x=None, y=None)  # status says resolved, no geometry
    with pytest.raises(psycopg.errors.CheckViolation):
        PostgresRepository(pg_dsn).upsert_many([bad])


def test_database_refuses_points_outside_the_envelope(pg_dsn, resolver):
    rows, _ = build_rows(issue(), resolver, "r")
    bad = dataclasses.replace(rows[0], x=5.0, y=5.0)  # looks like a degrees/metres mix-up
    with pytest.raises(psycopg.errors.CheckViolation):
        PostgresRepository(pg_dsn).upsert_many([bad])


def test_a_bad_row_rolls_back_the_whole_batch(pg_dsn, resolver):
    rows, _ = build_rows(issue(), resolver, "r")
    bad = dataclasses.replace(rows[2], x=5.0, y=5.0)
    with pytest.raises(psycopg.errors.CheckViolation):
        PostgresRepository(pg_dsn).upsert_many([rows[0], rows[1], bad])
    assert query(pg_dsn, "select count(*) from iris_staging.signal_ingest") == [(0,)]


def test_validation_queries_pass_after_a_real_run(pg_dsn, resolver):
    harvest(pg_dsn, resolver, "run-1")
    text = (SQL_DIR / "validation_queries.sql").read_text(encoding="utf-8")
    checked = 0
    for block in text.split("-- name:")[1:]:
        name, _, sql = block.partition("\n")
        rows = query(pg_dsn, sql)
        if "expect: no rows" in sql:
            checked += 1
            assert rows == [], f"{name.strip()} returned {rows[:3]}"
    assert checked == 7
