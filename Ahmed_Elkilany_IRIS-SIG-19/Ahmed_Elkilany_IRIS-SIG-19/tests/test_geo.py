import math

import pytest
from pyproj import Transformer

from conftest import ROOT
from gazette_harvester.geo import Gazetteer, GeoResolver, normalize_name, project


def write_csv(tmp_path, body):
    p = tmp_path / "gaz.csv"
    p.write_text("ags,name,aliases,lon,lat\n" + body, encoding="utf-8")
    return p


def test_normalize_name():
    assert normalize_name("Nußloch") == normalize_name("Nussloch")
    assert normalize_name("Reichenbach a. H.") == normalize_name("reichenbach a.h.".replace("a.h.", "a. h."))
    assert normalize_name("Stadt Ellwangen") == "ellwangen"
    assert normalize_name("Schönau") != normalize_name("Schonau")


def test_resolved_point_is_epsg25832_and_round_trips(resolver):
    res = resolver.resolve("Bammental")
    assert res.status == "resolved"
    back = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True).transform(res.x, res.y)
    assert back == pytest.approx((8.77583, 49.35083), abs=1e-5)
    assert 370_000 < res.x < 640_000 and 5_240_000 < res.y < 5_540_000


def test_aliases_and_ags(resolver):
    for name in ("Reichenbach a. H.", "Reichenbach am Heuberg", "reichenbach a.h."):
        res = resolver.resolve(name)
        assert (res.status, res.ags) == ("resolved", "08327040"), name
    assert resolver.resolve("Wiesenbach (Baden)").status == "resolved"


def test_unknown_place_is_unresolved_not_guessed(resolver):
    res = resolver.resolve("Musterstadt")
    assert res.status == "unresolved" and res.x is None and "Musterstadt" in res.note


def test_ambiguous_names_are_not_resolved(tmp_path):
    gaz, problems = Gazetteer.from_csv(write_csv(
        tmp_path,
        "08111001,Reichenbach an der Fils,Reichenbach,9.4,48.7\n08327040,Reichenbach am Heuberg,Reichenbach,8.84,48.13\n"))
    assert problems == []
    res = GeoResolver(gaz).resolve("Reichenbach")
    assert res.status == "ambiguous" and res.x is None
    assert "08111001" in res.note and "08327040" in res.note


def test_bad_gazetteer_rows_are_reported_and_never_projected(tmp_path):
    gaz, problems = Gazetteer.from_csv(write_csv(
        tmp_path,
        "1,Nowhere,,80.0,10.0\n2,Notanumber,,abc,48.0\n3,Berlinish,,13.4,52.5\n4,Fine,,9.0,48.5\n4,Dupe,,9.1,48.6\n,,,9,48\n"))
    assert len(problems) == 5
    assert sum("outside" in p for p in problems) == 2
    assert sum("not numeric" in p for p in problems) == 1
    assert sum("duplicate AGS" in p for p in problems) == 1
    assert sum("empty name" in p for p in problems) == 1
    r = GeoResolver(gaz)
    for name in ("Nowhere", "Notanumber", "Berlinish"):
        res = r.resolve(name)
        assert res.status == "invalid_coordinates" and res.x is None and res.y is None
    assert r.resolve("Fine").status == "resolved"
    assert r.resolve("Dupe").status == "unresolved"


@pytest.mark.parametrize("lon, lat", [(float("nan"), 48.0), (13.4, 52.5), (0.0, 0.0), (9.0, 90.0)])
def test_project_rejects_implausible_input(lon, lat):
    assert project(lon, lat) is None


def test_project_accepts_stuttgart():
    x, y = project(9.18, 48.78)
    assert math.isfinite(x) and 500_000 < x < 520_000 and 5_400_000 < y < 5_410_000


def test_shipped_gazetteer_loads_clean():
    gaz, problems = Gazetteer.from_csv(ROOT / "data" / "gazetteer_sample.csv")
    assert problems == [] and len(gaz.entries) == 6
