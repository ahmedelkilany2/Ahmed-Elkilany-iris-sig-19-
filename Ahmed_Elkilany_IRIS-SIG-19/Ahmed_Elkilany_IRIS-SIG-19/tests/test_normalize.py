from datetime import date

from gazette_harvester.geo import Gazetteer, GeoResolver
from gazette_harvester.models import Issue
from gazette_harvester.normalize import build_rows


def issue(**kw):
    base = dict(publication_slug="amtsblatt-bammental",
                publication_title="Gemeindenachrichten Amtsblatt der Gemeinden Bammental, Wiesenbach und Gaiberg",
                issue_no=43, issue_year=2026, published_on=date(2026, 10, 21),
                source_url="https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-bammental",
                access_level="paywalled", flags=[])
    base.update(kw)
    return Issue(**base)


def test_one_row_per_municipality_with_stable_ids(resolver):
    rows, problems = build_rows(issue(), resolver, "run1")
    assert problems == []
    assert [r.external_id for r in rows] == [
        "amtsblatt-bammental/2026-43/bammental",
        "amtsblatt-bammental/2026-43/wiesenbach",
        "amtsblatt-bammental/2026-43/gaiberg",
    ]
    assert rows[2].municipality_ags == "08226022"
    assert rows[0].title.endswith("Ausgabe 43/2026")
    assert rows[0].raw["access_level"] == "paywalled"
    assert "not harvested" in rows[0].raw["note"]


def test_hash_is_stable_across_runs_and_sensitive_to_content(resolver):
    a, _ = build_rows(issue(), resolver, "run1")
    b, _ = build_rows(issue(), resolver, "run2")
    c, _ = build_rows(issue(published_on=date(2026, 10, 22)), resolver, "run3")
    assert [r.content_hash for r in a] == [r.content_hash for r in b]
    assert a[0].content_hash != c[0].content_hash
    assert a[0].external_id == c[0].external_id  # same record, new content


def test_missing_issue_number_falls_back_to_the_date(resolver):
    rows, _ = build_rows(issue(issue_no=None, issue_year=None), resolver, "r")
    assert rows[0].external_id == "amtsblatt-bammental/2026-10-21/bammental"
    assert rows[0].title.endswith("vom 2026-10-21")


def test_invalid_gazetteer_coordinates_never_reach_a_row(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("ags,name,aliases,lon,lat\n1,Bammental,,80.0,10.0\n", encoding="utf-8")
    gaz, _ = Gazetteer.from_csv(p)
    rows, problems = build_rows(issue(publication_title="Amtsblatt der Gemeinde Bammental"), GeoResolver(gaz), "r")
    assert rows[0].geo_status == "invalid_coordinates" and rows[0].x is None and rows[0].y is None
    assert "geo_invalid_coordinates" in rows[0].quality_flags
    assert [p.code for p in problems] == ["geo_invalid_coordinates"]


def test_no_municipality_means_no_rows(resolver):
    rows, problems = build_rows(issue(publication_title="Irgendwas", publication_slug=""), resolver, "r")
    assert rows == [] and problems[0].code == "no_municipality"
