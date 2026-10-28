"""Build the gazetteer CSV from a municipality polygon file (GeoJSON).

Intended input is the BKG VG250 municipality layer (VG250_GEM, dl-de/by-2-0) or the state
survey's equivalent, exported to GeoJSON, for example:

    ogr2ogr -f GeoJSON vg250_gem.geojson VG250_GEM.shp -t_srs EPSG:4326 -where "SN_L='08' AND GF=4"

Each municipality gets a representative point (guaranteed to lie inside the polygon, unlike
a plain centroid for odd shapes). Needs shapely: pip install ".[gis]"
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from pyproj import Transformer


def build_gazetteer(geojson_path, out_csv, crs: str = "EPSG:4326", aliases_path=None,
                    ags_field: str = "AGS", name_field: str = "GEN", ags_prefix: str = "08") -> int:
    from shapely.geometry import shape  # imported here so the rest of the package works without shapely

    to_wgs84 = None if crs.upper() == "EPSG:4326" else Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    aliases: dict[str, list[str]] = {}
    if aliases_path:
        with open(aliases_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                aliases.setdefault(row["ags"].strip(), []).append(row["alias"].strip())

    data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    rows = []
    for feat in data["features"]:
        props = feat.get("properties") or {}
        ags = str(props.get(ags_field, "")).strip()
        name = str(props.get(name_field, "")).strip()
        if not ags.startswith(ags_prefix) or not name:
            continue
        pt = shape(feat["geometry"]).representative_point()
        lon, lat = (to_wgs84.transform(pt.x, pt.y) if to_wgs84 else (pt.x, pt.y))
        rows.append((ags, name, "|".join(aliases.get(ags, [])), f"{lon:.6f}", f"{lat:.6f}",
                     f"{Path(geojson_path).name} representative point"))

    rows.sort()
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ags", "name", "aliases", "lon", "lat", "source"])
        w.writerows(rows)
    return len(rows)
