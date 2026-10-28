"""HTML parsing for the NUSSBAUM.de Kiosk pages.

I deliberately key on the visible text pattern ("Ausgabe 43/2026", "vom 21. Oktober 2026")
and not on CSS classes. The site is a JS-heavy app whose class names look generated, so
text is the more stable thing to rely on. If the markup changes in a way that breaks this,
the parser returns zero issues and the pipeline reports `no_issues_found` instead of
loading garbage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Issue, Problem

MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8,
    "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11, "dezember": 12, "dez": 12,
}

ISSUE_RE = re.compile(r"^(?:Aktuell:\s*)?Ausgabe\s+(\d{1,3})\s*/\s*(\d{4})$")
DATE_RE = re.compile(r"\bvom\s+(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\.?\s+(\d{4})\b")
PUBLICATION_PATH_RE = re.compile(r"^/kiosk/mitteilungsblaetter/([^/?#]+)/?$")
SEGMENT_WINDOW = 8  # text nodes after an issue heading that can belong to that issue
SKIP_TAGS = {"script", "style", "noscript", "template"}
INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


@dataclass
class ParseResult:
    title: str | None
    issues: list[Issue] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _tokens(soup: BeautifulSoup) -> list[str]:
    out = []
    for node in soup.find_all(string=True):
        if node.parent is not None and node.parent.name in SKIP_TAGS:
            continue
        text = " ".join(str(node).translate(INVISIBLE).split())
        if text:
            out.append(text)
    return out


def parse_german_date(day: str, month: str, year: str) -> date | None:
    m = MONTHS.get(month.strip(".").lower())
    if not m:
        return None
    try:
        return date(int(year), m, int(day))
    except ValueError:
        return None


def parse_index_page(html: str, base_url: str) -> list[str]:
    """Return the publication page URLs linked from the Kiosk index."""
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base_url).netloc
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        if urlparse(full).netloc == host and PUBLICATION_PATH_RE.match(urlparse(full).path):
            seen[full.split("#")[0].split("?")[0]] = None
    return list(seen)


def parse_publication_page(html: str, url: str, today: date | None = None) -> ParseResult:
    today = today or date.today()
    soup = BeautifulSoup(html, "lxml")
    slug_match = PUBLICATION_PATH_RE.match(urlparse(url).path)
    slug = slug_match.group(1) if slug_match else urlparse(url).path.rstrip("/").split("/")[-1]

    h1 = soup.find("h1")
    title = " ".join(h1.get_text(" ").translate(INVISIBLE).split()) if h1 else ""
    result = ParseResult(title=title or None)
    if not title:
        result.problems.append(Problem("missing_title", "no <h1> found, cannot name the publication", url, "error"))
        return result

    tokens = _tokens(soup)
    segments: list[tuple[int, int, list[str]]] = []
    for tok in tokens:
        m = ISSUE_RE.match(tok)
        if m:
            segments.append((int(m.group(1)), int(m.group(2)), []))
        elif segments and len(segments[-1][2]) < SEGMENT_WINDOW:
            segments[-1][2].append(tok)

    if not segments:
        result.problems.append(Problem("no_issues_found", "page parsed but no 'Ausgabe NN/YYYY' entries present", url))
        return result

    seen: set[tuple[int, int]] = set()
    for no, year, body in segments:
        label = f"Ausgabe {no}/{year}"
        if (no, year) in seen:
            result.problems.append(Problem("duplicate_issue_in_page", f"{label} listed more than once", url))
            continue
        seen.add((no, year))

        text = " ".join(body)
        dm = DATE_RE.search(text)
        published = parse_german_date(*dm.groups()) if dm else None
        if published is None:
            reason = "no 'vom <date>' text" if not dm else f"unparsable date '{dm.group(0)}'"
            result.problems.append(Problem("bad_publication_date", f"{label}: {reason}", url, "error"))
            continue
        if published > today + timedelta(days=1):
            result.problems.append(
                Problem("publication_date_in_future", f"{label} dated {published} is after today ({today})", url, "error")
            )
            continue
        if published.year < 2000:
            result.problems.append(Problem("publication_date_implausible", f"{label} dated {published}", url, "error"))
            continue

        flags: list[str] = []
        iso = published.isocalendar()
        if iso.year == year and abs(iso.week - no) > 1:
            flags.append("issue_number_vs_calendar_week_mismatch")
        if abs(published.year - year) > 1 or (published.year != year and 2 <= published.month <= 11):
            flags.append("issue_year_vs_date_mismatch")

        result.issues.append(
            Issue(
                publication_slug=slug,
                publication_title=title,
                issue_no=no,
                issue_year=year,
                published_on=published,
                source_url=url,
                access_level="paywalled" if "NUSSBAUM+" in body else "free",
                flags=flags,
            )
        )
    return result
