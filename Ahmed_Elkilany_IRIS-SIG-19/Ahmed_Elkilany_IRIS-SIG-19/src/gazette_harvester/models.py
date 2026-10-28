from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Problem:
    """Anything worth showing in the error/quality report."""

    code: str
    detail: str
    url: str | None = None
    severity: str = "warning"  # warning | error

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "detail": self.detail, "url": self.url}


@dataclass
class Issue:
    """One gazette issue as listed on a publication's Kiosk page."""

    publication_slug: str
    publication_title: str
    issue_no: int | None
    issue_year: int | None
    published_on: date
    source_url: str
    access_level: str  # 'paywalled' | 'free'
    flags: list[str] = field(default_factory=list)


@dataclass
class StagingRow:
    source_id: str
    signal_type: str
    external_id: str
    title: str
    published_on: date
    source_url: str
    publication_slug: str
    issue_no: int | None
    issue_year: int | None
    municipality_name: str
    municipality_ags: str | None
    region: str
    x: float | None
    y: float | None
    geo_status: str
    geo_note: str | None
    access_level: str
    quality_flags: list[str]
    content_hash: str
    raw: dict
    harvest_run_id: str
