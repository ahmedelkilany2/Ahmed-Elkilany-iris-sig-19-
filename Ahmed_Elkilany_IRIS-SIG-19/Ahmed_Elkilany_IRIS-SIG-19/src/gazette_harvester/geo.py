"""Municipality name -> EPSG:25832 point, using a local gazetteer CSV.

I'm not calling an online geocoder on purpose: names like "Reichenbach" or "Schönau" exist
several times in Baden-Württemberg, a free-text geocoder will happily pick one, and that
would be a silent wrong answer. A gazetteer keyed by name/alias lets me say "ambiguous" or
"unresolved" explicitly.

CSV columns: ags,name,aliases,lon,lat   (lon/lat in WGS84, aliases separated by '|')
`gazette-harvester build-gazetteer` can produce this from a municipality polygon file.
"""
from __future__ import annotations

import csv
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pyproj import Transformer

# sanity envelopes, deliberately a bit wider than the state itself
BW_LON = (7.4, 10.6)
BW_LAT = (47.4, 49.9)
UTM32_X = (370_000.0, 640_000.0)
UTM32_Y = (5_240_000.0, 5_540_000.0)

_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
_TRANSLIT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def normalize_name(name: str) -> str:
    s = name.casefold().strip()
    for k, v in _TRANSLIT.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(stadt|gemeinde)\s+", "", s)
    return s


@dataclass
class GazetteerEntry:
    ags: str
    name: str
    lon: float | None
    lat: float | None
    aliases: list[str] = field(default_factory=list)
    row_problem: str | None = None  # set when the coordinates in the file are unusable


@dataclass
class GeoResult:
    status: str  # resolved | ambiguous | unresolved | invalid_coordinates
    x: float | None = None
    y: float | None = None
    ags: str | None = None
    note: str | None = None


def project(lon: float, lat: float) -> tuple[float, float] | None:
    """WGS84 -> EPSG:25832, or None if the input or output is not plausible for BW."""
    if not (isinstance(lon, float) and isinstance(lat, float)) or math.isnan(lon) or math.isnan(lat):
        return None
    if not (BW_LON[0] <= lon <= BW_LON[1] and BW_LAT[0] <= lat <= BW_LAT[1]):
        return None
    x, y = _TO_UTM.transform(lon, lat)
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (UTM32_X[0] <= x <= UTM32_X[1] and UTM32_Y[0] <= y <= UTM32_Y[1]):
        return None
    return round(x, 2), round(y, 2)


class Gazetteer:
    def __init__(self, entries: list[GazetteerEntry]):
        self.entries = entries
        self._index: dict[str, list[GazetteerEntry]] = {}
        for e in entries:
            for key in {normalize_name(e.name), *(normalize_name(a) for a in e.aliases)}:
                if key:
                    self._index.setdefault(key, []).append(e)

    @classmethod
    def from_csv(cls, path: str | Path) -> tuple["Gazetteer", list[str]]:
        problems: list[str] = []
        entries: list[GazetteerEntry] = []
        seen_ags: set[str] = set()
        with open(path, newline="", encoding="utf-8") as fh:
            for lineno, row in enumerate(csv.DictReader(fh), start=2):
                name = (row.get("name") or "").strip()
                ags = (row.get("ags") or "").strip()
                if not name:
                    problems.append(f"line {lineno}: empty name, skipped")
                    continue
                if ags and ags in seen_ags:
                    problems.append(f"line {lineno}: duplicate AGS {ags} ({name}), skipped")
                    continue
                seen_ags.add(ags)
                aliases = [a.strip() for a in (row.get("aliases") or "").split("|") if a.strip()]
                try:
                    lon, lat = float(row["lon"]), float(row["lat"])
                    bad = None if project(lon, lat) else "coordinates outside Baden-Württemberg envelope"
                except (TypeError, ValueError, KeyError):
                    lon = lat = None
                    bad = "coordinates missing or not numeric"
                if bad:
                    problems.append(f"line {lineno}: {name}: {bad}")
                entries.append(GazetteerEntry(ags, name, lon, lat, aliases, bad))
        return cls(entries), problems

    def lookup(self, name: str) -> list[GazetteerEntry]:
        return self._index.get(normalize_name(name), [])


class GeoResolver:
    def __init__(self, gazetteer: Gazetteer):
        self.gazetteer = gazetteer

    def resolve(self, name: str) -> GeoResult:
        hits = self.gazetteer.lookup(name)
        if not hits:
            return GeoResult("unresolved", note=f"'{name}' not in gazetteer")
        if len(hits) > 1:
            candidates = ", ".join(f"{h.name} ({h.ags})" for h in hits)
            return GeoResult("ambiguous", note=f"'{name}' matches several entries: {candidates}")
        hit = hits[0]
        if hit.row_problem:
            return GeoResult("invalid_coordinates", ags=hit.ags, note=f"{hit.name}: {hit.row_problem}")
        xy = project(hit.lon, hit.lat)
        if xy is None:  # cannot happen after from_csv, but never trust silently
            return GeoResult("invalid_coordinates", ags=hit.ags, note=f"{hit.name}: projection failed")
        return GeoResult("resolved", x=xy[0], y=xy[1], ags=hit.ags or None)
