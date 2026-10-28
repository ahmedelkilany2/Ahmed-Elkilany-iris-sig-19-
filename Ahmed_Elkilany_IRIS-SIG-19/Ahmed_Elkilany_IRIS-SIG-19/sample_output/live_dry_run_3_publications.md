# Harvest run 20261028T044210Z-4b960e

Started 2026-10-28T04:42:10+00:00, finished 2026-10-28T04:46:11+00:00

## Source findings

- **gazetteer**: gazetteer_sample.csv: 6 entries, 0 warnings
- **legacy_endpoint**: {'url': 'https://lokalmatador.de/bekanntmachungen', 'status': 200, 'final_url': 'https://www.nussbaum.de/meine-heimat/startseite', 'redirect_chain': ['https://lokalmatador.de/bekanntmachungen', 'https://www.lokalmatador.de/bekanntmachungen', 'https://www.nussbaum.de', 'https://www.nussbaum.de/meine-heimat'], 'verdict': 'obsolete_redirect', 'detail': 'lokalmatador.de/bekanntmachungen now redirects to www.nussbaum.de/meine-heimat/startseite'}
- **publication_discovery**: sitemap (377 publication pages)

## Counters

| counter | value |
|---|---|
| geo_unresolved | 39 |
| issues_parsed | 39 |
| issues_rejected | 0 |
| publications_discovered | 377 |
| publications_fetched | 3 |
| rows_built | 39 |
| rows_inserted | 39 |
| rows_unchanged | 0 |
| rows_updated | 0 |

## Problems by type

| severity | code | count |
|---|---|---|
| warning | geo_unresolved | 39 |
| warning | sitemap_children_truncated | 1 |

## Problem detail

- [warning] `sitemap_children_truncated` 1362 publication sitemaps listed, reading the first 20 (https://services.www.nussbaum.de/sitemap_archive.xml)
- [warning] `geo_unresolved` x13 'Althengstett' not in gazetteer (publication 'amtsblatt-althengstett') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-althengstett)
- [warning] `geo_unresolved` x13 'Hausen ob Verena' not in gazetteer (publication 'amtsblatt-hausen-ob-verena') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-hausen-ob-verena)
- [warning] `geo_unresolved` x13 'Wendlingen am Neckar' not in gazetteer (publication 'amtsblatt-wendlingen') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-wendlingen)
