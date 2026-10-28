import shutil

import pytest

from conftest import BASE, INDEX, SITE, TODAY, FakeRepo
from gazette_harvester.discovery import SitemapError, discover_from_sitemaps, parse_sitemap
from gazette_harvester.http import FixtureFetcher
from gazette_harvester.pipeline import run_harvest

SITEMAPS = SITE.parent / "sitemap"


class CountingFetcher(FixtureFetcher):
    def __init__(self, root):
        super().__init__(root)
        self.requested = []

    def get(self, url, check_robots=True, accept="html"):
        self.requested.append(url)
        return super().get(url, check_robots, accept)


def test_parse_sitemap_index_and_urlset():
    kind, locs = parse_sitemap((SITEMAPS / "sitemap.xml").read_text(encoding="utf-8"))
    assert kind == "index" and len(locs) == 3
    kind, locs = parse_sitemap((SITEMAPS / "sitemap_publications_2024-01-01.xml").read_text(encoding="utf-8"))
    assert kind == "urlset" and len(locs) == 6


def test_parse_sitemap_with_encoding_declaration():
    kind, locs = parse_sitemap('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://a/b</loc></url></urlset>')
    assert (kind, locs) == ("urlset", ["https://a/b"])


@pytest.mark.parametrize("bad", ["", "<html><body>no</body></html>", "<urlset><url></urlset>", "<rss/>"])
def test_parse_sitemap_rejects_garbage(bad):
    with pytest.raises(SitemapError):
        parse_sitemap(bad)


def test_external_entities_are_not_expanded():
    evil = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&e;</loc></url></urlset>')
    _, locs = parse_sitemap(evil)
    assert all("root:" not in loc for loc in locs)


def test_discovers_only_real_publication_pages_and_reads_only_publication_sitemaps():
    fetcher, problems = CountingFetcher(SITEMAPS), []
    urls = discover_from_sitemaps(fetcher, INDEX, problems)
    assert urls == [f"{BASE}/amtsblatt-bammental", f"{BASE}/amtsblatt-wehingen", f"{BASE}/lokalzeitung-sillenbuch"]
    assert problems == []
    # the news/event/obituary sitemaps are listed but never requested
    assert [u.rsplit("/", 1)[-1] for u in fetcher.requested] == [
        "sitemap.xml", "sitemap_archive.xml", "sitemap_publications_2026-08-08.xml", "sitemap_publications_2024-01-01.xml"]


def test_unreadable_sitemap_is_reported_and_others_still_used(tmp_path):
    shutil.copytree(SITEMAPS, tmp_path, dirs_exist_ok=True)
    (tmp_path / "sitemap.xml").unlink()
    (tmp_path / "sitemap_publications_2026-08-08.xml").write_text("<html>oops</html>")
    problems = []
    urls = discover_from_sitemaps(FixtureFetcher(tmp_path), INDEX, problems)
    assert len(urls) == 3
    assert sorted(p.code for p in problems) == ["sitemap_http_404", "sitemap_malformed"]


def test_no_sitemap_declared_returns_nothing(tmp_path):
    assert discover_from_sitemaps(FixtureFetcher(tmp_path), INDEX, []) == []


def test_pipeline_uses_sitemap_discovery_and_survives_a_missing_page(tmp_path, resolver):
    shutil.copytree(SITE, tmp_path, dirs_exist_ok=True)
    shutil.copytree(SITEMAPS, tmp_path, dirs_exist_ok=True)
    rep = run_harvest(fetcher=FixtureFetcher(tmp_path), repo=FakeRepo(), resolver=resolver, run_id="t",
                      index_url=INDEX, today=TODAY)
    assert rep.source_findings["publication_discovery"] == "sitemap (3 publication pages)"
    assert rep.counters["publications_discovered"] == 3
    assert rep.counters["publications_failed"] == 1          # lokalzeitung-sillenbuch has no page in the fixtures
    assert rep.counters["rows_inserted"] == 75
    assert [(p.code, p.severity) for p in rep.problems] == [("http_404", "error")]


def test_index_page_is_the_fallback_when_sitemaps_give_nothing(site_fetcher, fake_repo, resolver):
    rep = run_harvest(fetcher=site_fetcher, repo=fake_repo, resolver=resolver, run_id="t", index_url=INDEX, today=TODAY)
    assert rep.source_findings["publication_discovery"] == "index page (2 links)"


def test_sitemap_file_cap_is_configurable_and_reported():
    problems = []
    urls = discover_from_sitemaps(FixtureFetcher(SITEMAPS), INDEX, problems, max_children=1)
    assert len(urls) == 1  # only the first publications sitemap was read
    assert [p.code for p in problems] == ["sitemap_children_truncated"]
