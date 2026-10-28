"""Turn parsed issues into staging rows (one row per issue and municipality)."""
from __future__ import annotations

import hashlib
import json

from .geo import GeoResolver, normalize_name
from .models import Issue, Problem, StagingRow
from .municipalities import municipalities_from_title

SOURCE_ID = "nussbaum_kiosk"
SIGNAL_TYPE = "municipal_gazette_issue"
REGION = "Baden-Württemberg"


def _hash(parts: dict) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_rows(issue: Issue, resolver: GeoResolver, run_id: str) -> tuple[list[StagingRow], list[Problem]]:
    problems: list[Problem] = []
    names, inferred = municipalities_from_title(issue.publication_title, issue.publication_slug)
    if not names:
        problems.append(
            Problem("no_municipality", f"could not derive a municipality for '{issue.publication_title}'", issue.source_url, "error")
        )
        return [], problems

    label = f"Ausgabe {issue.issue_no}/{issue.issue_year}" if issue.issue_no else f"vom {issue.published_on.isoformat()}"
    issue_key = (
        f"{issue.issue_year}-{issue.issue_no:02d}" if issue.issue_no and issue.issue_year else issue.published_on.isoformat()
    )

    rows: list[StagingRow] = []
    for name in names:
        geo = resolver.resolve(name)
        flags = list(issue.flags)
        if inferred:
            flags.append("municipality_inferred_from_url_slug")
        if geo.status != "resolved":
            flags.append(f"geo_{geo.status}")
            problems.append(
                Problem(f"geo_{geo.status}", f"{geo.note} (publication '{issue.publication_slug}')", issue.source_url)
            )

        external_id = f"{issue.publication_slug}/{issue_key}/{normalize_name(name).replace(' ', '-')}"
        title = f"{issue.publication_title} – {label}"
        raw = {
            "publication_title": issue.publication_title,
            "publication_slug": issue.publication_slug,
            "issue_label": label,
            "published_on": issue.published_on.isoformat(),
            "municipalities_in_title": names,
            "access_level": issue.access_level,
            "note": "issue-level record; notice text is inside the paywalled E-Paper and is not harvested",
        }
        rows.append(
            StagingRow(
                source_id=SOURCE_ID,
                signal_type=SIGNAL_TYPE,
                external_id=external_id,
                title=title,
                published_on=issue.published_on,
                source_url=issue.source_url,
                publication_slug=issue.publication_slug,
                issue_no=issue.issue_no,
                issue_year=issue.issue_year,
                municipality_name=name,
                municipality_ags=geo.ags,
                region=REGION,
                x=geo.x,
                y=geo.y,
                geo_status=geo.status,
                geo_note=geo.note,
                access_level=issue.access_level,
                quality_flags=sorted(flags),
                content_hash=_hash(
                    {
                        "title": title,
                        "published_on": issue.published_on.isoformat(),
                        "source_url": issue.source_url,
                        "municipality": name,
                        "ags": geo.ags,
                        "geo_status": geo.status,
                        "x": geo.x,
                        "y": geo.y,
                        "access": issue.access_level,
                        "flags": sorted(flags),
                    }
                ),
                raw=raw,
                harvest_run_id=run_id,
            )
        )
    return rows, problems
