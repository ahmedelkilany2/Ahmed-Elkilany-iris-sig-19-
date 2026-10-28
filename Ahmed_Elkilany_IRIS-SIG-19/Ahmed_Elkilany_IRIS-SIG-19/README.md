# IRIS-SIG-19: Nussbaum Medien gazette harvester

Ahmed Elkilany, candidate assignment for IRIS.

This is a Python harvester that reads the public gazette pages on nussbaum.de, cleans the data and loads it
into `iris_staging.signal_ingest` (PostgreSQL 16 / PostGIS 3.4) with point geometry in EPSG:25832. Re-running it
does not create duplicates.

**Read this first:** the endpoint in the brief no longer works, and the text of the notices sits behind a paid
subscription. So the harvester collects *gazette issues* (which gazette, which issue, which date, which
municipalities) and not the individual notices. Section 2 explains why and what I would do next.

## 1. What I found when I checked the source

I checked the source before writing the parser, on 27 and 28 October 2026.

| Item | Brief | What I found |
|---|---|---|
| Endpoint | `https://lokalmatador.de/bekanntmachungen` | It redirects four times and ends on `https://www.nussbaum.de/meine-heimat/startseite`, a general start page with no notice list. The old HTML selectors cannot work any more. |
| Where the gazettes are now | not stated | The NUSSBAUM.de "Kiosk": one page per gazette at `/kiosk/mitteilungsblaetter/<slug>`. |
| What is public there | not stated | Gazette title, issue number (`Ausgabe 43/2026`), issue date (`vom 21. Oktober 2026`) and a `NUSSBAUM+` label. About 13 issues are listed per gazette. |
| What is not public | not stated | The content of the issues. The pages are marked as paid content, and the site FAQ says non-subscribers only get the titles that are freely accessible. |
| robots.txt | not stated | `/kiosk/` is allowed for normal crawlers with `Crawl-delay: 10`. Some paths (`/api/`, `/auth/`, `/mein-konto` and others) are disallowed, and a list of AI and SEO crawlers is blocked completely. The harvester uses its own user agent, waits 10 seconds between requests and keeps the number of requests low. |
| List of gazettes | not stated | The Kiosk index page is rendered by JavaScript and has no links in the HTML. robots.txt points to sitemaps, and the archive sitemap lists `sitemap_publications_*.xml` files with the gazette pages. My live run found 377 of them, which is close to the "380+ municipalities" in the brief. |

`python -m gazette_harvester probe` repeats the endpoint check, and every `harvest` run writes the same result into
its report.

I also ran the harvester against the live site as a dry run (nothing written to the database): 377 pages discovered,
3 fetched, 39 issues parsed, 0 rejected. The report is in `sample_output/live_dry_run_3_publications.md`.

## 2. What the harvester collects, and why

The brief asks for municipal notices. The notices are inside the paid E-Paper, and the brief says not to bypass
access restrictions. I do not log in, do not open the "Ausgabe lesen" links and never read issue content.

What is public is the issue list. Each issue becomes one signal of type `municipal_gazette_issue`: "gazette X
published issue N on date D for municipalities A, B, C". It keeps the identifiers, titles, publication dates, source
URLs and geographic context the brief asks for, and every value can be checked on the public page.

A gazette that covers several municipalities (for example Bammental, Wiesenbach and Gaiberg) produces one row per
issue and municipality, so each municipality gets its own point.

What this does not give is the content of the notices. For that, the next step would be to ask Nussbaum Medien for a
licensed feed, or to read the official notice pages that individual municipalities publish on their own websites.
I did not build either.

## 3. Data mapping

The brief names `iris_staging.signal_ingest` but not its columns, so `sql/001_signal_ingest.sql` is my own proposal.
If the real table is different, only `repository.py` needs to change.

| Column | Where it comes from |
|---|---|
| `source_id` | fixed value `nussbaum_kiosk` |
| `signal_type` | fixed value `municipal_gazette_issue` |
| `external_id` | `<slug>/<year>-<issue>/<municipality>`, for example `amtsblatt-bammental/2026-43/gaiberg` |
| `title` | the page title plus `Ausgabe 43/2026` |
| `published_on` | the `vom 21. Oktober 2026` text, parsed with my own German month table so it does not depend on the computer's locale |
| `source_url` | the Kiosk page that lists the issue (there is no public URL per issue) |
| `municipality_name`, `municipality_ags` | taken from the gazette title; the AGS code comes from the gazetteer when it is known |
| `geom` | `geometry(Point, 25832)`, only when the location was resolved |
| `geo_status`, `geo_note` | `resolved`, `ambiguous`, `unresolved` or `invalid_coordinates`, with the reason |
| `access_level` | `paywalled` if the issue has the NUSSBAUM+ label, otherwise `free` |
| `quality_flags` | for example `geo_unresolved` or `issue_number_vs_calendar_week_mismatch` |
| `content_hash`, `harvest_run_id` | change detection and traceability |
| `raw` | jsonb with the parsed source values |

The database also protects itself: `(source_id, external_id)` is unique, a point exists only when `geo_status` is
`resolved`, and the geometry must fall inside a rough UTM 32N box around Baden-Württemberg. A mix-up between degrees
and metres is rejected by PostgreSQL even if my code missed it.

## 4. How to run it

You need Python 3.11 or newer and PostgreSQL 16 with PostGIS 3.4. A `docker-compose.yml` is included for the database.

Windows (PowerShell), from the project folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env          # then edit .env; there are no credentials in the code
docker compose up -d            # or use your own PostgreSQL with PostGIS

python -m gazette_harvester init-db
python -m gazette_harvester probe
python -m gazette_harvester harvest --limit-publications 3 --max-issues 5
python -m gazette_harvester validate
```

macOS or Linux is the same, with `source .venv/bin/activate` and `cp` instead of `copy`. After `pip install`
the command `gazette-harvester` also works instead of `python -m gazette_harvester`.

Offline demo that needs no access to the site:

```
python -m gazette_harvester harvest --fixtures tests/fixtures/site --dry-run
python -m gazette_harvester harvest --fixtures tests/fixtures/site
python -m gazette_harvester harvest --fixtures tests/fixtures/edge --publications-file tests/fixtures/edge_publications.txt
```

The last command uses broken pages on purpose, to show the error handling.

Options for `harvest`: `--since YYYY-MM-DD`, `--max-issues N` (newest N per gazette), `--limit-publications N`,
`--publications-file`, `--gazetteer`, `--max-sitemap-files N`, `--dry-run`, `--out DIR`. Each run writes a JSON and a
Markdown report to `reports/`.

Exit codes: `0` clean, `3` finished but with errors in the report, `2` nothing could be fetched, `1` bad configuration.

Settings are read from environment variables or `.env`: `IRIS_DATABASE_URL`, `HARVEST_USER_AGENT` (please put a
contact address in it), `HARVEST_MIN_DELAY_SECONDS` (default 10), `HARVEST_TIMEOUT_SECONDS`, `HARVEST_MAX_RETRIES`,
`HARVEST_INDEX_URL`.

## 5. Tests

```
python -m pytest
```

Without a database this gives 79 passed and 8 skipped. The 8 skipped tests need PostGIS and run when
`IRIS_TEST_DSN` is set. They drop and recreate the `iris_staging` schema, so use an empty scratch database:

```
IRIS_TEST_DSN=postgresql://user:password@localhost:5432/scratch python -m pytest
```

All 87 tests passed against PostgreSQL 16.15 with PostGIS 3.4.2.

What is covered:

- parsing, using fixtures plus deliberately broken pages (impossible, missing and future dates, duplicate issues,
  missing title, empty page, page without issues)
- finding the municipalities in a gazette title
- geocoding: aliases, ambiguous names, unknown names, bad coordinates, and the projection round trip
- HTTP behaviour: retries, `Retry-After`, timeouts, robots.txt, crawl delay, redirects
- sitemap discovery, including a test that XML entities are not expanded
- the whole pipeline, including re-runs and one publication failing while the others continue
- in PostGIS: a re-run adds nothing, changed content updates in place, bad rows are rejected, and a failed batch
  is rolled back completely

I also broke the content hash on purpose to check that the re-run tests fail when idempotency is broken.

## 6. How it works

**Idempotency.** Rows are written with `INSERT ... ON CONFLICT (source_id, external_id) DO UPDATE ... WHERE
content_hash IS DISTINCT FROM EXCLUDED.content_hash`. Running the same input again inserts nothing and updates
nothing (`sample_output/run_2_identical_rerun.md`: 0 inserted, 0 updated, 75 unchanged). If the source changes a date or
a title, the existing row is updated. The hash contains only source data, never run-specific values, so
`harvest_run_id` means "the run that last changed this row".

**One transaction per gazette.** If one row is rejected, nothing from that gazette is written and the run moves on
to the next one.

**Being polite to the site.** The harvester sends its own user agent, waits at least 10 seconds between requests to
the same host (or whatever `Crawl-delay` the host asks for, if that is larger), and retries timeouts and 429 or 5xx
answers with growing waits, respecting `Retry-After`. Other 4xx answers are not retried. robots.txt is read per host:
a missing file means no limits, but a file that is forbidden or unreadable means the host is skipped. Nothing logs in
or follows paywall links.

**Finding the gazettes.** In this order: the sitemaps listed in robots.txt (only the `sitemap_publications_*` files),
then the links on the Kiosk index page, then `config/publications.txt`. The method that was used is written to the
report.

**Locations.** Municipality names are looked up in a local gazetteer CSV (`ags,name,aliases,lon,lat`) and projected
from WGS84 to EPSG:25832 with pyproj. I did not use an online geocoder because several municipality names exist more
than once in Baden-Württemberg, and a free-text geocoder would pick one without telling anyone. Here a name that
matches several entries is `ambiguous`, an unknown name is `unresolved`, and in both cases no point is stored.
Coordinates that are not numbers, are NaN, or fall outside Baden-Württemberg are marked `invalid_coordinates`, both
when the gazetteer is loaded and again when a name is resolved.

`data/gazetteer_sample.csv` only has the 6 municipalities used in the fixtures. Their coordinates come from Wikipedia
and GeoNames and are good to a few hundred metres, which is enough for the demo but not authoritative. For real use,
build a gazetteer from official boundaries (BKG VG250 municipalities, exported to GeoJSON):

```
pip install -e ".[gis]"
python -m gazette_harvester build-gazetteer bw_gem.geojson --out data/gazetteer.csv
python -m gazette_harvester harvest --gazetteer data/gazetteer.csv
```

Abbreviations such as "Reichenbach a. H." are not in official name lists. They can be added with `--aliases`
(a CSV with the columns `ags,alias`). Anything that is not found shows up as `unresolved` in the report.

**The report.** Every run writes counters (discovered, fetched, failed, parsed, rejected, inserted, updated, unchanged,
location results) and a list of problems with code, severity, details and URL. Identical problems are listed once with
a count. Examples of codes: `bad_publication_date`, `publication_date_in_future`, `duplicate_issue_in_page`,
`empty_response`, `no_issues_found`, `missing_title`, `blocked_by_robots`, `network_failure`, `http_404`,
`geo_unresolved`, `geo_ambiguous`, `geo_invalid_coordinates`, `load_failed`.

## 7. Known limitations

- **Issues, not notices.** This is the biggest gap compared to the wording of the brief (see section 2).
- **Fixtures are reconstructed.** The HTML in `tests/fixtures/site` was rebuilt from the rendered page text, not
  saved from the raw page. The parser relies on the visible text pattern and on the `<h1>` title, and it worked on
  the live site in my dry run (3 gazettes). If the markup ever changes, it reports `no_issues_found` or `missing_title`
  and does not load wrong data.
- **I did not run a live load into a database.** The live run was a dry run. Loading into PostGIS was tested with the
  fixtures.
- **Sample gazetteer.** With only 6 municipalities, almost all rows from the live site come out as `unresolved`
  until a gazetteer is built from the official boundaries (section 6).
- **Sitemap depth.** The archive sitemap lists 1362 daily `sitemap_publications_*` files. Reading all of them would take
  hours at a 10 second delay, so the first 20 are read by default and the report says
  `sitemap_children_truncated`. That gave 377 gazette pages. Whether older files add more can be checked with
  `--max-sitemap-files 40`.
- **Run time.** A full run is one request per gazette, so roughly an hour at the crawl delay. Use
  `--limit-publications` while developing.
- **Only the newest issues.** Each page lists about 13 issues and has a "Mehr anzeigen" button that I do not use.
  Gazettes are weekly, so running at least once a week catches every new issue. The back catalogue is not covered.
- **Municipality names come from titles.** Titles that name no place fall back to the URL slug and get the flag
  `municipality_inferred_from_url_slug`. The sitemap also contains local newspapers and similar titles, not only
  municipal gazettes, so the discovered count can differ from the figure in the brief.
- **Table layout is assumed** (section 3).
- **Issue date.** `vom <date>` is the date printed by the publisher. I compare it with the calendar week of the issue
  number and flag mismatches, but the real online publication time is not known.

## 8. Project layout

```
src/gazette_harvester/   config, http, discovery, parse, municipalities, geo, gazetteer_build,
                         normalize, repository, pipeline, report, source_check, cli
sql/                     001_signal_ingest.sql, validation_queries.sql
data/gazetteer_sample.csv    config/publications.txt
tests/                   unit, pipeline and PostGIS tests; fixtures/site (real structure), fixtures/edge (broken on purpose),
                         fixtures/sitemap
tools/make_fixtures.py   rebuilds the HTML fixtures
sample_output/           outputs of the runs described in error_quality_report.md
```
