-- Validation queries for iris_staging.signal_ingest.
-- Blocks marked "expect: no rows" must return nothing; `gazette-harvester validate` flags them if not.

-- name: row_counts_by_geo_status
SELECT geo_status, count(*) AS rows
FROM iris_staging.signal_ingest
GROUP BY geo_status ORDER BY geo_status;

-- name: duplicate_natural_keys
-- expect: no rows
SELECT source_id, external_id, count(*)
FROM iris_staging.signal_ingest
GROUP BY source_id, external_id HAVING count(*) > 1;

-- name: wrong_srid_or_invalid_geometry
-- expect: no rows
SELECT id, external_id FROM iris_staging.signal_ingest
WHERE geom IS NOT NULL
  AND (ST_SRID(geom) <> 25832 OR NOT ST_IsValid(geom) OR GeometryType(geom) <> 'POINT');

-- name: points_outside_bw_envelope
-- expect: no rows
SELECT id, external_id, ST_AsText(ST_Transform(geom, 4326)) AS wgs84
FROM iris_staging.signal_ingest
WHERE geom IS NOT NULL
  AND NOT (ST_X(ST_Transform(geom, 4326)) BETWEEN 7.4 AND 10.6
       AND ST_Y(ST_Transform(geom, 4326)) BETWEEN 47.4 AND 49.9);

-- name: geometry_and_geo_status_disagree
-- expect: no rows
SELECT id, external_id, geo_status FROM iris_staging.signal_ingest
WHERE (geo_status = 'resolved') <> (geom IS NOT NULL);

-- name: missing_mandatory_fields
-- expect: no rows
SELECT id, external_id FROM iris_staging.signal_ingest
WHERE coalesce(title, '') = '' OR coalesce(source_url, '') = ''
   OR coalesce(municipality_name, '') = '' OR published_on IS NULL;

-- name: future_or_implausible_publication_dates
-- expect: no rows
SELECT id, external_id, published_on FROM iris_staging.signal_ingest
WHERE published_on > current_date + 1 OR published_on < DATE '2000-01-01';

-- name: joint_gazette_members_more_than_25km_apart
-- expect: no rows
SELECT a.publication_slug, a.municipality_name AS a_name, b.municipality_name AS b_name,
       round(ST_Distance(a.geom, b.geom)) AS metres
FROM iris_staging.signal_ingest a
JOIN iris_staging.signal_ingest b
  ON a.publication_slug = b.publication_slug AND a.issue_year = b.issue_year
 AND a.issue_no = b.issue_no AND a.id < b.id
WHERE a.geom IS NOT NULL AND b.geom IS NOT NULL AND ST_Distance(a.geom, b.geom) > 25000;

-- name: locations_not_resolved
SELECT publication_slug, municipality_name, geo_status, geo_note, count(*) AS rows
FROM iris_staging.signal_ingest
WHERE geo_status <> 'resolved'
GROUP BY 1, 2, 3, 4 ORDER BY 1, 2;

-- name: issues_per_publication
SELECT publication_slug, count(DISTINCT (issue_year, issue_no)) AS issues,
       min(published_on) AS first_issue, max(published_on) AS latest_issue
FROM iris_staging.signal_ingest
GROUP BY publication_slug ORDER BY publication_slug;

-- name: quality_flags_seen
SELECT flag, count(*) FROM iris_staging.signal_ingest, unnest(quality_flags) AS flag
GROUP BY flag ORDER BY 2 DESC;
