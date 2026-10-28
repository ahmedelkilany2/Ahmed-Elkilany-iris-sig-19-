-- Staging table for harvested signals.
-- ASSUMPTION: the brief names iris_staging.signal_ingest but not its columns, so this
-- is my proposed shape. If the real table differs, only repository.py needs to change.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS iris_staging;

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest (
    id                bigserial PRIMARY KEY,
    source_id         text        NOT NULL,
    signal_type       text        NOT NULL,
    external_id       text        NOT NULL,
    title             text        NOT NULL,
    published_on      date        NOT NULL,
    source_url        text        NOT NULL,
    publication_slug  text        NOT NULL,
    issue_no          integer,
    issue_year        integer,
    municipality_name text        NOT NULL,
    municipality_ags  text,
    region            text        NOT NULL DEFAULT 'Baden-Württemberg',
    geom              geometry(Point, 25832),
    geo_status        text        NOT NULL,
    geo_note          text,
    access_level      text        NOT NULL,
    quality_flags     text[]      NOT NULL DEFAULT '{}',
    content_hash      text        NOT NULL,
    raw               jsonb       NOT NULL,
    harvest_run_id    text        NOT NULL,
    ingested_at       timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT signal_ingest_natural_key UNIQUE (source_id, external_id),
    CONSTRAINT signal_ingest_geo_status_chk
        CHECK (geo_status IN ('resolved', 'ambiguous', 'unresolved', 'invalid_coordinates')),
    -- a point exists if and only if the location was resolved
    CONSTRAINT signal_ingest_geom_matches_status_chk
        CHECK ((geo_status = 'resolved') = (geom IS NOT NULL)),
    -- rough UTM 32N envelope around Baden-Württemberg, last line of defence
    CONSTRAINT signal_ingest_geom_bbox_chk
        CHECK (geom IS NULL OR (
            ST_X(geom) BETWEEN 370000 AND 640000 AND
            ST_Y(geom) BETWEEN 5240000 AND 5540000))
);

CREATE INDEX IF NOT EXISTS signal_ingest_geom_gix
    ON iris_staging.signal_ingest USING gist (geom);
CREATE INDEX IF NOT EXISTS signal_ingest_published_idx
    ON iris_staging.signal_ingest (published_on DESC);
