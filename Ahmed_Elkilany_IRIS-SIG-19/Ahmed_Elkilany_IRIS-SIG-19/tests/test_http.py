import pytest
import requests
import responses

from gazette_harvester.http import FetchError, PoliteFetcher
from gazette_harvester.source_check import probe_endpoint

PAGE = "https://www.nussbaum.de/kiosk/mitteilungsblaetter/amtsblatt-x"
ROBOTS = "https://www.nussbaum.de/robots.txt"
HTML = {"content_type": "text/html; charset=utf-8"}


def make(**kw):
    sleeps = []
    f = PoliteFetcher("test-harvester/1.0", min_delay=2.0, max_retries=kw.pop("max_retries", 3),
                      sleep=sleeps.append, clock=lambda: 0.0, **kw)
    return f, sleeps


@responses.activate
def test_success_sends_user_agent_and_respects_min_delay():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, body="<h1>x</h1>", **HTML)
    f, sleeps = make()
    res = f.get(PAGE)
    assert res.status == 200 and "<h1>" in res.text
    assert responses.calls[-1].request.headers["User-Agent"] == "test-harvester/1.0"
    assert 2.0 in sleeps  # throttled between the robots.txt request and the page request


@responses.activate
def test_retries_5xx_with_backoff_then_succeeds():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, status=503)
    responses.add(responses.GET, PAGE, status=502)
    responses.add(responses.GET, PAGE, body="ok", **HTML)
    f, sleeps = make()
    assert f.get(PAGE).text == "ok"
    assert [c.request.url for c in responses.calls].count(PAGE) == 3
    assert 1.5 in sleeps and 3.0 in sleeps  # exponential backoff


@responses.activate
def test_429_honours_retry_after():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, PAGE, body="ok", **HTML)
    f, sleeps = make()
    f.get(PAGE)
    assert 7 in sleeps


@responses.activate
def test_gives_up_after_max_retries():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, body=requests.ConnectionError("boom"))
    f, _ = make(max_retries=2)
    with pytest.raises(FetchError) as exc:
        f.get(PAGE)
    assert exc.value.code == "network_failure"
    assert [c.request.url for c in responses.calls].count(PAGE) == 3


@responses.activate
def test_timeout_is_retried_like_any_network_error():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, body=requests.Timeout("slow"))
    responses.add(responses.GET, PAGE, body="late but fine", **HTML)
    f, _ = make()
    assert f.get(PAGE).text == "late but fine"


@responses.activate
def test_client_errors_are_not_retried():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, status=404)
    f, _ = make()
    with pytest.raises(FetchError) as exc:
        f.get(PAGE)
    assert exc.value.code == "http_404"
    assert [c.request.url for c in responses.calls].count(PAGE) == 1


@responses.activate
def test_robots_disallow_means_the_page_is_never_requested():
    responses.add(responses.GET, ROBOTS, body="User-agent: *\nDisallow: /kiosk/\n")
    f, _ = make()
    with pytest.raises(FetchError) as exc:
        f.get(PAGE)
    assert exc.value.code == "blocked_by_robots"
    assert PAGE not in [c.request.url for c in responses.calls]


@responses.activate
def test_robots_specific_to_our_agent_is_honoured():
    responses.add(responses.GET, ROBOTS, body="User-agent: test-harvester\nDisallow: /\n")
    f, _ = make()
    with pytest.raises(FetchError):
        f.get(PAGE)


@responses.activate
def test_unreadable_robots_fails_closed():
    responses.add(responses.GET, ROBOTS, status=500)
    f, _ = make(max_retries=1)
    with pytest.raises(FetchError) as exc:
        f.get(PAGE)
    assert exc.value.code == "blocked_by_robots"


@responses.activate
def test_non_html_response_is_rejected():
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, PAGE, body="{}", content_type="application/json")
    f, _ = make()
    with pytest.raises(FetchError) as exc:
        f.get(PAGE)
    assert exc.value.code == "unexpected_content_type"


@responses.activate
def test_probe_detects_the_obsolete_endpoint_redirect():
    """What the brief's URL actually does: it lands on the nussbaum.de start page."""
    legacy = "https://lokalmatador.de/bekanntmachungen"
    home = "https://www.nussbaum.de/meine-heimat/startseite"
    responses.add(responses.GET, "https://lokalmatador.de/robots.txt", status=404)
    responses.add(responses.GET, legacy, status=301, headers={"Location": home})
    responses.add(responses.GET, home, body="<h1>NUSSBAUM</h1>", **HTML)
    f, _ = make()
    finding = probe_endpoint(f, legacy)
    assert finding["verdict"] == "obsolete_redirect"
    assert finding["final_url"] == home and finding["redirect_chain"] == [legacy]


@responses.activate
def test_probe_reports_blocked_endpoint_without_raising():
    responses.add(responses.GET, "https://lokalmatador.de/robots.txt", body="User-agent: *\nDisallow: /\n")
    f, _ = make()
    assert probe_endpoint(f, "https://lokalmatador.de/bekanntmachungen")["verdict"] == "unreachable_or_blocked"


@responses.activate
def test_probe_reachable_when_nothing_moved():
    url = "https://example.org/bekanntmachungen"
    responses.add(responses.GET, "https://example.org/robots.txt", status=404)
    responses.add(responses.GET, url, body="<h1>ok</h1>", **HTML)
    f, _ = make()
    assert probe_endpoint(f, url)["verdict"] == "reachable"


@responses.activate
def test_crawl_delay_from_robots_is_honoured_when_larger_than_ours():
    responses.add(responses.GET, ROBOTS, body="User-agent: *\nCrawl-delay: 10\n")
    responses.add(responses.GET, PAGE, body="a", **HTML)
    responses.add(responses.GET, PAGE + "2", body="b", **HTML)
    f, sleeps = make()
    f.get(PAGE)
    f.get(PAGE + "2")
    assert sleeps.count(10.0) == 2  # before the first page and before the second
    assert 2.0 not in sleeps


@responses.activate
def test_our_delay_wins_when_robots_asks_for_less():
    responses.add(responses.GET, ROBOTS, body="User-agent: *\nCrawl-delay: 1\n")
    responses.add(responses.GET, PAGE, body="a", **HTML)
    f, sleeps = make()
    f.get(PAGE)
    assert 2.0 in sleeps and 1.0 not in sleeps


@responses.activate
def test_delay_is_tracked_per_host():
    other = "https://services.example.org/sitemap.xml"
    responses.add(responses.GET, ROBOTS, body="User-agent: *\nCrawl-delay: 10\n")
    responses.add(responses.GET, PAGE, body="a", **HTML)
    responses.add(responses.GET, "https://services.example.org/robots.txt", status=404)
    responses.add(responses.GET, other, body="<urlset/>", content_type="application/xml")
    f, sleeps = make()
    f.get(PAGE)
    sleeps.clear()
    f.get(other, accept="xml")
    assert 10.0 not in sleeps  # the other host has no crawl delay and its first request is not throttled by ours


@responses.activate
def test_sitemaps_are_read_from_robots():
    responses.add(responses.GET, ROBOTS, body="User-agent: *\nSitemap: https://services.www.nussbaum.de/sitemap.xml\n")
    f, _ = make()
    assert f.sitemaps_for(PAGE) == ["https://services.www.nussbaum.de/sitemap.xml"]


@responses.activate
def test_xml_is_accepted_only_when_asked_for():
    url = "https://www.nussbaum.de/sitemap.xml"
    responses.add(responses.GET, ROBOTS, status=404)
    responses.add(responses.GET, url, body="<urlset/>", content_type="application/xml; charset=utf-8")
    f, _ = make()
    with pytest.raises(FetchError) as exc:
        f.get(url)
    assert exc.value.code == "unexpected_content_type"
    assert f.get(url, accept="xml").text == "<urlset/>"
