from __future__ import annotations

from datetime import date

import psycopg

from .discovery import discover_from_sitemaps
from .geo import GeoResolver
from .http import FetchError
from .models import Problem
from .normalize import build_rows
from .parse import parse_index_page, parse_publication_page
from .report import RunReport


def discover_publications(fetcher, index_url: str, fallback_urls: list[str], report: RunReport,
                          max_sitemap_files: int | None = None) -> list[str]:
    """Sitemaps first, then the Kiosk index page, then the seed list. Which one was used goes in the report."""
    problems: list[Problem] = []
    kw = {"max_children": max_sitemap_files} if max_sitemap_files else {}
    urls = discover_from_sitemaps(fetcher, index_url, problems, **kw)
    report.add(problems)
    if urls:
        report.source_findings["publication_discovery"] = f"sitemap ({len(urls)} publication pages)"
        return urls

    try:
        res = fetcher.get(index_url)
        urls = parse_index_page(res.text, res.final_url)
        if urls:
            report.source_findings["publication_discovery"] = f"index page ({len(urls)} links)"
            return urls
        report.add([Problem("index_no_links", "index page has no publication links (probably rendered by JavaScript); using the seed list", index_url)])
    except FetchError as exc:
        report.add([Problem(f"index_{exc.code}", f"could not read index, using the seed list: {exc.detail}", index_url, "error")])
    report.source_findings["publication_discovery"] = f"seed list ({len(fallback_urls)} entries)"
    return list(fallback_urls)


def run_harvest(
    *,
    fetcher,
    repo,
    resolver: GeoResolver,
    run_id: str,
    index_url: str,
    publication_urls: list[str] | None = None,
    fallback_urls: list[str] | None = None,
    today: date | None = None,
    since: date | None = None,
    limit_publications: int | None = None,
    max_issues: int | None = None,
    max_sitemap_files: int | None = None,
    source_findings: dict | None = None,
) -> RunReport:
    today = today or date.today()
    report = RunReport(run_id, source_findings=source_findings or {})
    c = report.counters

    urls = publication_urls or discover_publications(fetcher, index_url, fallback_urls or [], report, max_sitemap_files)
    urls = list(dict.fromkeys(urls))
    c["publications_discovered"] = len(urls)
    if limit_publications:
        urls = urls[:limit_publications]
    if not urls:
        report.add([Problem("no_publications", "nothing to harvest: no links on the index and no seed list", index_url, "error")])
        report.finish()
        return report

    for url in urls:
        try:
            page = fetcher.get(url)
        except FetchError as exc:
            c["publications_failed"] += 1
            report.add([Problem(exc.code, exc.detail or "fetch failed", url, "error")])
            continue

        if not page.text.strip():
            c["publications_empty"] += 1
            report.add([Problem("empty_response", "HTTP 200 with an empty body", url)])
            continue
        c["publications_fetched"] += 1

        parsed = parse_publication_page(page.text, url, today=today)
        report.add(parsed.problems)
        c["issues_rejected"] += sum(
            1 for p in parsed.problems if p.code in {"bad_publication_date", "publication_date_in_future", "publication_date_implausible"}
        )

        issues = parsed.issues
        c["issues_parsed"] += len(issues)
        if since:
            kept = [i for i in issues if i.published_on >= since]
            c["issues_skipped_before_since"] += len(issues) - len(kept)
            issues = kept
        if max_issues:
            issues = sorted(issues, key=lambda i: i.published_on, reverse=True)[:max_issues]

        rows, seen = [], set()
        for issue in issues:
            built, problems = build_rows(issue, resolver, run_id)
            report.add(problems)
            for row in built:
                if row.external_id in seen:
                    c["rows_duplicate_in_source"] += 1
                    report.add([Problem("duplicate_row_in_source", row.external_id, url)])
                    continue
                seen.add(row.external_id)
                rows.append(row)
                c[f"geo_{row.geo_status}"] += 1
        c["rows_built"] += len(rows)

        try:
            counts = repo.upsert_many(rows)
        except psycopg.Error as exc:
            c["publications_load_failed"] += 1
            # the geo counters above were for rows that did not land, so say so loudly
            report.add([Problem("load_failed", f"{type(exc).__name__}: {exc}".strip(), url, "error")])
            continue
        c["rows_inserted"] += counts.inserted
        c["rows_updated"] += counts.updated
        c["rows_unchanged"] += counts.unchanged

    report.finish()
    return report
