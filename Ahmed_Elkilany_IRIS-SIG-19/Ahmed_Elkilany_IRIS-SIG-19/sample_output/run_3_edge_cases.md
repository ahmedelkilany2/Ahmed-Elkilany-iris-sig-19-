# Harvest run 20261027T105937Z-94c44a

Started 2026-10-27T10:59:37+00:00, finished 2026-10-27T10:59:37+00:00

## Source findings

- **gazetteer**: gazetteer_sample.csv: 6 entries, 0 warnings
- **mode**: offline fixtures from tests/fixtures/edge

## Counters

| counter | value |
|---|---|
| geo_unresolved | 3 |
| issues_parsed | 3 |
| issues_rejected | 4 |
| publications_discovered | 5 |
| publications_empty | 1 |
| publications_failed | 1 |
| publications_fetched | 3 |
| rows_built | 3 |
| rows_inserted | 3 |
| rows_unchanged | 0 |
| rows_updated | 0 |

## Problems by type

| severity | code | count |
|---|---|---|
| error | bad_publication_date | 3 |
| error | http_404 | 1 |
| error | missing_title | 1 |
| error | publication_date_in_future | 1 |
| warning | duplicate_issue_in_page | 1 |
| warning | empty_response | 1 |
| warning | geo_unresolved | 3 |
| warning | no_issues_found | 1 |

## Problem detail

- [error] `bad_publication_date` Ausgabe 12/2026: unparsable date 'vom 31. Februar 2026' (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [error] `bad_publication_date` Ausgabe 13/2026: unparsable date 'vom 18. Smarch 2026' (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [error] `publication_date_in_future` Ausgabe 50/2026 dated 2026-12-30 is after today (2026-10-27) (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [warning] `duplicate_issue_in_page` Ausgabe 10/2026 listed more than once (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [error] `bad_publication_date` Ausgabe 14/2026: no 'vom <date>' text (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [warning] `geo_unresolved` 'Musterstadt' not in gazetteer (publication 'amtsblatt-musterstadt') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [warning] `geo_unresolved` 'Musterstadt' not in gazetteer (publication 'amtsblatt-musterstadt') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [warning] `geo_unresolved` 'Musterstadt' not in gazetteer (publication 'amtsblatt-musterstadt') (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-musterstadt)
- [warning] `empty_response` HTTP 200 with an empty body (https://www.nussbaum.de/kiosk/mitteilungsblaetter/empty-page)
- [warning] `no_issues_found` page parsed but no 'Ausgabe NN/YYYY' entries present (https://www.nussbaum.de/kiosk/mitteilungsblaetter/no-issues)
- [error] `missing_title` no <h1> found, cannot name the publication (https://www.nussbaum.de/kiosk/mitteilungsblaetter/no-title)
- [error] `http_404` no fixture kiosk_mitteilungsblaetter_amtsblatt-gibt-es-nicht.html (https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-gibt-es-nicht)
