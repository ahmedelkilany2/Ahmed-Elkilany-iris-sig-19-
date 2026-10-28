from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

from .config import Settings, load_dotenv
from .geo import Gazetteer, GeoResolver
from .http import FixtureFetcher, PoliteFetcher
from .pipeline import run_harvest
from .repository import DryRunRepository, PostgresRepository, SQL_DIR
from .source_check import probe_endpoint

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAZETTEER = ROOT / "data" / "gazetteer_sample.csv"
DEFAULT_SEEDS = ROOT / "config" / "publications.txt"


def _read_urls(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def _fetcher(settings: Settings):
    return PoliteFetcher(settings.user_agent, settings.min_delay, settings.timeout, settings.max_retries)


def cmd_init_db(args, settings) -> int:
    if not settings.database_url:
        print("IRIS_DATABASE_URL is not set", file=sys.stderr)
        return 1
    PostgresRepository(settings.database_url).init_schema()
    print("schema iris_staging / table signal_ingest ready")
    return 0


def cmd_probe(args, settings) -> int:
    fetcher = _fetcher(settings)
    out = {
        "legacy_endpoint": probe_endpoint(fetcher, settings.legacy_url),
        "kiosk_index": probe_endpoint(fetcher, settings.index_url),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_harvest(args, settings) -> int:
    gaz_path = Path(args.gazetteer or DEFAULT_GAZETTEER)
    gazetteer, gaz_problems = Gazetteer.from_csv(gaz_path)
    for p in gaz_problems:
        print(f"gazetteer warning: {p}", file=sys.stderr)

    findings = {"gazetteer": f"{gaz_path.name}: {len(gazetteer.entries)} entries, {len(gaz_problems)} warnings"}
    if args.fixtures:
        fetcher = FixtureFetcher(args.fixtures)
        findings["mode"] = f"offline fixtures from {args.fixtures}"
    else:
        fetcher = _fetcher(settings)
        findings["legacy_endpoint"] = probe_endpoint(fetcher, settings.legacy_url)

    if args.dry_run:
        repo = DryRunRepository()
    elif settings.database_url:
        repo = PostgresRepository(settings.database_url)
    else:
        print("IRIS_DATABASE_URL is not set (use --dry-run to skip the database)", file=sys.stderr)
        return 1

    explicit = _read_urls(Path(args.publications_file)) if args.publications_file else None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    report = run_harvest(
        fetcher=fetcher,
        repo=repo,
        resolver=GeoResolver(gazetteer),
        run_id=run_id,
        index_url=settings.index_url,
        publication_urls=explicit,
        fallback_urls=_read_urls(DEFAULT_SEEDS),
        since=date.fromisoformat(args.since) if args.since else None,
        limit_publications=args.limit_publications,
        max_issues=args.max_issues,
        max_sitemap_files=args.max_sitemap_files,
        source_findings=findings,
    )
    j, m = report.write(args.out)
    print(report.to_markdown())
    print(f"report written to {j} and {m}")

    if report.counters["publications_fetched"] == 0:
        return 2
    return 3 if report.error_count else 0


def cmd_build_gazetteer(args, settings) -> int:
    from .gazetteer_build import build_gazetteer

    n = build_gazetteer(args.geojson, args.out, crs=args.crs, aliases_path=args.aliases)
    print(f"wrote {n} municipalities to {args.out}")
    return 0


def cmd_validate(args, settings) -> int:
    if not settings.database_url:
        print("IRIS_DATABASE_URL is not set", file=sys.stderr)
        return 1
    text = (SQL_DIR / "validation_queries.sql").read_text(encoding="utf-8")
    blocks = [b for b in text.split("-- name:")[1:]]
    failed = False
    with psycopg.connect(settings.database_url) as conn:
        for block in blocks:
            name, _, sql = block.partition("\n")
            expect_empty = "expect: no rows" in sql
            rows = conn.execute(sql).fetchall()
            status = "ok" if not (expect_empty and rows) else "FAIL"
            failed |= status == "FAIL"
            print(f"\n[{status}] {name.strip()}")
            for r in rows[: args.limit]:
                print("   ", r)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    settings = Settings.from_env()
    ap = argparse.ArgumentParser(prog="gazette-harvester", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create schema/table if missing").set_defaults(fn=cmd_init_db)
    sub.add_parser("probe", help="check the brief's endpoint and the Kiosk index").set_defaults(fn=cmd_probe)

    h = sub.add_parser("harvest", help="fetch, parse, geocode and load")
    h.add_argument("--fixtures", help="read pages from a directory instead of the network")
    h.add_argument("--publications-file", help="file with one publication URL per line (skips index discovery)")
    h.add_argument("--gazetteer", help=f"gazetteer CSV (default {DEFAULT_GAZETTEER.name})")
    h.add_argument("--since", help="only issues published on/after this date (YYYY-MM-DD)")
    h.add_argument("--limit-publications", type=int)
    h.add_argument("--max-issues", type=int, help="newest N issues per publication")
    h.add_argument("--max-sitemap-files", type=int, help="how many publication sitemap files to read (default 20)")
    h.add_argument("--dry-run", action="store_true")
    h.add_argument("--out", default="reports")
    h.set_defaults(fn=cmd_harvest)

    g = sub.add_parser("build-gazetteer", help="make a gazetteer CSV from a municipality GeoJSON (needs shapely)")
    g.add_argument("geojson")
    g.add_argument("--out", default="data/gazetteer.csv")
    g.add_argument("--crs", default="EPSG:4326", help="CRS of the GeoJSON coordinates")
    g.add_argument("--aliases", help="optional CSV with columns ags,alias")
    g.set_defaults(fn=cmd_build_gazetteer)

    v = sub.add_parser("validate", help="run sql/validation_queries.sql")
    v.add_argument("--limit", type=int, default=10)
    v.set_defaults(fn=cmd_validate)

    args = ap.parse_args(argv)
    return args.fn(args, settings)
