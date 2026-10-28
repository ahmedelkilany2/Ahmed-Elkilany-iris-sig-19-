# Error and quality report

Two kinds of runs are described here: runs on the offline fixtures (loaded into PostgreSQL 16 / PostGIS 3.4)
and one live dry run against nussbaum.de.

The two main fixtures in `tests/fixtures/site` (Bammental with 13 issues, Wehingen with 12 issues) are rebuilt from the
live Kiosk pages. The `amtsblatt-musterstadt` page and the other files in `tests/fixtures/edge` are made up and only
exist to trigger the error handling. They are not part of `signal_ingest_sample.csv`.

## Fixture runs

| Run | Input | Result |
|---|---|---|
| 1, first load | `fixtures/site` | 2 gazettes, 25 issues, 75 rows (3 municipalities per issue), 75 inserted, 75 `resolved`, 0 problems |
| 2, identical re-run | `fixtures/site` | 0 inserted, 0 updated, 75 unchanged; the table still has 75 rows |
| 3, error cases | `fixtures/edge` plus one missing page | 5 gazettes requested: 3 fetched, 1 empty, 1 failed; 3 rows loaded, 4 issues rejected, 12 problems (below) |

Problems in run 3:

| Severity | Code | Count | What happens |
|---|---|---|---|
| error | `bad_publication_date` | 3 | `31. Februar`, an unknown month name, and no date at all. The issue is rejected and not loaded. |
| error | `publication_date_in_future` | 1 | Issue dated after the run date. Rejected. |
| error | `missing_title` | 1 | No `<h1>`, so the gazette cannot be identified. Nothing is loaded. |
| error | `http_404` | 1 | Gazette page missing. The other gazettes continue. |
| warning | `duplicate_issue_in_page` | 1 | The same issue is listed twice. The first one is kept. |
| warning | `empty_response` | 1 | HTTP 200 with an empty body. |
| warning | `no_issues_found` | 1 | Page read, but no issue entries found. |
| warning | `geo_unresolved` | 3 | "Musterstadt" is not in the gazetteer. The rows are kept with `geo_status = 'unresolved'` and no point. |

Run 3 ends with exit code 3 (finished, with errors).

## Live dry run (28 October 2026)

`live_dry_run_3_publications.md`: 377 gazette pages found through the sitemaps, 3 fetched, 39 issues parsed, none
rejected. The 39 `geo_unresolved` warnings are expected: Althengstett, Hausen ob Verena and Wendlingen am Neckar are not
in the 6-row sample gazetteer. They are listed, not guessed. This was a dry run, so nothing was written to the database.

## Data quality checks

`validation_results.txt` was produced after the three fixture runs, so its counts include the 3 made-up Musterstadt
rows (78 rows in total, while the sample CSV has the 75 rows from the real-structure fixtures). All 7 checks that must
return no rows pass:

- no duplicate natural keys
- no wrong SRID or invalid geometry
- no point outside the Baden-Württemberg box
- geometry and `geo_status` always agree
- no missing mandatory fields
- no future or implausible dates
- members of a joint gazette are never more than 25 km apart (a spatial check on the coordinates)

All 25 issue dates from the real-structure fixtures agree with the calendar week of their issue number, so none of them
has a quality flag. The one `issue_number_vs_calendar_week_mismatch` comes from the made-up page.

## Not checked

- A live load into the database (the live run was a dry run).
- The sample gazetteer coordinates are approximate and come from public references, not from an official boundary file.
