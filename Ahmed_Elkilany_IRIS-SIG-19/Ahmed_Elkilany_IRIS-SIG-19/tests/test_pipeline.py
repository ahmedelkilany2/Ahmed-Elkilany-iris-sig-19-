import shutil
from datetime import date

import psycopg
import pytest

from conftest import BASE, EDGE, INDEX, SITE, TODAY, FakeRepo
from gazette_harvester.geo import Gazetteer, GeoResolver
from gazette_harvester.http import FixtureFetcher
from gazette_harvester.pipeline import run_harvest


def run(fetcher, repo, resolver, **kw):
    kw.setdefault("today", TODAY)
    return run_harvest(fetcher=fetcher, repo=repo, resolver=resolver, run_id=kw.pop("run_id", "t1"),
                       index_url=INDEX, **kw)


def codes(report):
    return sorted(p.code for p in report.problems)


def test_first_run_loads_everything_with_points(site_fetcher, fake_repo, resolver):
    rep = run(site_fetcher, fake_repo, resolver)
    c = rep.counters
    assert (c["publications_discovered"], c["publications_fetched"]) == (2, 2)
    # 13 Bammental issues x 3 municipalities + 12 Wehingen issues x 3 municipalities
    assert c["rows_built"] == c["rows_inserted"] == 75
    assert c["geo_resolved"] == 75
    assert rep.problems == []
    assert all(r.x is not None and r.geo_status == "resolved" for r in fake_repo.store.values())


def test_rerun_does_not_duplicate_or_update(site_fetcher, fake_repo, resolver):
    run(site_fetcher, fake_repo, resolver, run_id="first")
    again = run(site_fetcher, fake_repo, resolver, run_id="second")
    assert again.counters["rows_inserted"] == 0
    assert again.counters["rows_updated"] == 0
    assert again.counters["rows_unchanged"] == 75
    assert len(fake_repo.store) == 75


def test_changed_source_updates_only_the_affected_rows(tmp_path, fake_repo, resolver):
    shutil.copytree(SITE, tmp_path, dirs_exist_ok=True)
    run(FixtureFetcher(tmp_path), fake_repo, resolver)

    page = tmp_path / "kiosk_mitteilungsblaetter_amtsblatt-bammental.html"
    page.write_text(page.read_text(encoding="utf-8").replace("21. Oktober", "22. Oktober"), encoding="utf-8")
    rep = run(FixtureFetcher(tmp_path), fake_repo, resolver, run_id="later")
    assert (rep.counters["rows_inserted"], rep.counters["rows_updated"], rep.counters["rows_unchanged"]) == (0, 3, 72)
    assert len(fake_repo.store) == 75


def test_since_filter(site_fetcher, fake_repo, resolver):
    rep = run(site_fetcher, fake_repo, resolver, since=date(2026, 10, 1))
    assert rep.counters["rows_built"] == 9  # issues 41-43 of Bammental, 3 municipalities each
    assert rep.counters["issues_skipped_before_since"] == 10 + 12


def test_max_issues_keeps_the_newest(site_fetcher, fake_repo, resolver):
    run(site_fetcher, fake_repo, resolver, max_issues=2)
    dates = sorted({r.published_on for r in fake_repo.store.values() if r.publication_slug == "amtsblatt-bammental"})
    assert dates == [date(2026, 10, 14), date(2026, 10, 21)]


def test_one_failing_publication_does_not_stop_the_run(site_fetcher, fake_repo, resolver):
    urls = [f"{BASE}/amtsblatt-gibt-es-nicht", f"{BASE}/amtsblatt-bammental"]
    rep = run(site_fetcher, fake_repo, resolver, publication_urls=urls)
    assert rep.counters["publications_failed"] == 1 and rep.counters["rows_inserted"] == 39
    assert [(p.code, p.severity) for p in rep.problems] == [("http_404", "error")]


def test_unresolvable_municipality_is_kept_visible(fake_repo, resolver):
    rep = run(FixtureFetcher(EDGE), fake_repo, resolver, publication_urls=[f"{BASE}/amtsblatt-musterstadt"])
    rows = list(fake_repo.store.values())
    assert len(rows) == 3
    assert all(r.geo_status == "unresolved" and r.x is None and r.y is None for r in rows)
    assert all("municipality_inferred_from_url_slug" in r.quality_flags for r in rows)
    assert rep.counters["geo_unresolved"] == 3
    assert codes(rep).count("geo_unresolved") == 3
    assert rep.counters["issues_rejected"] == 4  # impossible date, unknown month, no date, future date


def test_empty_response_and_pages_without_issues(fake_repo, resolver):
    urls = [f"{BASE}/empty-page", f"{BASE}/no-issues", f"{BASE}/no-title"]
    rep = run(FixtureFetcher(EDGE), fake_repo, resolver, publication_urls=urls)
    assert rep.counters["rows_built"] == 0 and fake_repo.store == {}
    assert rep.counters["publications_empty"] == 1
    assert codes(rep) == ["empty_response", "missing_title", "no_issues_found"]


def test_index_without_links_falls_back_to_seed_list(tmp_path, fake_repo, resolver):
    shutil.copytree(SITE, tmp_path, dirs_exist_ok=True)
    (tmp_path / "kiosk_mitteilungsblaetter.html").write_text("<html><body><h1>JS app shell</h1></body></html>")
    rep = run(FixtureFetcher(tmp_path), fake_repo, resolver, fallback_urls=[f"{BASE}/amtsblatt-wehingen"])
    assert "index_no_links" in codes(rep)
    assert rep.counters["rows_inserted"] == 36


def test_missing_index_is_reported_as_error_and_seed_list_used(tmp_path, fake_repo, resolver):
    shutil.copytree(SITE, tmp_path, dirs_exist_ok=True)
    (tmp_path / "kiosk_mitteilungsblaetter.html").unlink()
    rep = run(FixtureFetcher(tmp_path), fake_repo, resolver, fallback_urls=[f"{BASE}/amtsblatt-bammental"])
    assert ("index_http_404", "error") in [(p.code, p.severity) for p in rep.problems]
    assert rep.counters["rows_inserted"] == 39


def test_nothing_to_do_is_an_error(site_fetcher, fake_repo, resolver, tmp_path):
    rep = run(FixtureFetcher(tmp_path), fake_repo, resolver)
    assert "no_publications" in codes(rep) and rep.error_count == 2


def test_database_failure_is_recorded_and_run_continues(site_fetcher, resolver):
    repo = FakeRepo(fail_with=psycopg.OperationalError("connection lost"))
    rep = run(site_fetcher, repo, resolver)
    assert rep.counters["publications_load_failed"] == 2 and rep.counters["rows_inserted"] == 0
    assert codes(rep) == ["load_failed", "load_failed"]


def test_report_serialises(site_fetcher, fake_repo, resolver, tmp_path):
    rep = run(site_fetcher, fake_repo, resolver)
    json_path, md_path = rep.write(tmp_path)
    assert json_path.read_text().startswith("{") and "rows_inserted" in md_path.read_text()


def test_report_lists_identical_problems_once_with_a_count(fake_repo, resolver, tmp_path):
    rep = run(FixtureFetcher(EDGE), fake_repo, resolver, publication_urls=[f"{BASE}/amtsblatt-musterstadt"])
    assert codes(rep).count("geo_unresolved") == 3                       # raw list keeps every occurrence
    grouped = [p for p in rep.as_dict()["problems"] if p["code"] == "geo_unresolved"]
    assert len(grouped) == 1 and grouped[0]["count"] == 3
    assert "`geo_unresolved` x3" in rep.to_markdown()
    assert {s["code"]: s["count"] for s in rep.as_dict()["problem_summary"]}["geo_unresolved"] == 3
