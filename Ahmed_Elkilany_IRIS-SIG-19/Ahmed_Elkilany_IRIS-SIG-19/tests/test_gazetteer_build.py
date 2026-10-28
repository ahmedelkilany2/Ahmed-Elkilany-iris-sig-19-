import csv
import json

import pytest
from pyproj import Transformer

pytest.importorskip("shapely")
from gazette_harvester.gazetteer_build import build_gazetteer
from gazette_harvester.geo import Gazetteer, GeoResolver


def square(cx, cy, d=0.02):
    return {"type": "Polygon", "coordinates": [[[cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d], [cx - d, cy + d], [cx - d, cy - d]]]}


def test_builds_bw_only_gazetteer_the_resolver_can_use(tmp_path):
    src = tmp_path / "gem.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"AGS": "08327040", "GEN": "Reichenbach am Heuberg"}, "geometry": square(8.84, 48.13)},
        {"type": "Feature", "properties": {"AGS": "08226008", "GEN": "Bammental"}, "geometry": square(8.78, 49.35)},
        {"type": "Feature", "properties": {"AGS": "09162000", "GEN": "München"}, "geometry": square(11.5, 48.1)},
    ]}))
    aliases = tmp_path / "aliases.csv"
    aliases.write_text("ags,alias\n08327040,Reichenbach a. H.\n")
    out = tmp_path / "gaz.csv"

    assert build_gazetteer(src, out, aliases_path=aliases) == 2  # Bavaria filtered out
    gaz, problems = Gazetteer.from_csv(out)
    assert problems == []
    res = GeoResolver(gaz).resolve("Reichenbach a. H.")
    assert (res.status, res.ags) == ("resolved", "08327040")
    assert GeoResolver(gaz).resolve("München").status == "unresolved"


def test_reprojects_from_utm_input(tmp_path):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True).transform(8.78, 49.35)
    src = tmp_path / "gem.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"AGS": "08226008", "GEN": "Bammental"}, "geometry": square(x, y, 1000)}]}))
    out = tmp_path / "gaz.csv"
    build_gazetteer(src, out, crs="EPSG:25832")
    row = next(csv.DictReader(open(out, encoding="utf-8")))
    assert (float(row["lon"]), float(row["lat"])) == pytest.approx((8.78, 49.35), abs=1e-4)
