from datetime import date

from conftest import BASE, EDGE, SITE, TODAY
from gazette_harvester.parse import parse_german_date, parse_index_page, parse_publication_page


def read(path):
    return path.read_text(encoding="utf-8")


def test_index_links_are_deduplicated_and_filtered():
    urls = parse_index_page(read(SITE / "kiosk_mitteilungsblaetter.html"), BASE)
    assert urls == [f"{BASE}/amtsblatt-bammental", f"{BASE}/amtsblatt-wehingen"]


def test_bammental_page():
    res = parse_publication_page(read(SITE / "kiosk_mitteilungsblaetter_amtsblatt-bammental.html"),
                                 f"{BASE}/amtsblatt-bammental", today=TODAY)
    assert res.problems == []
    assert len(res.issues) == 13
    newest = res.issues[0]
    assert (newest.issue_no, newest.issue_year, newest.published_on) == (43, 2026, date(2026, 10, 21))
    assert newest.publication_slug == "amtsblatt-bammental"
    assert all(i.access_level == "paywalled" for i in res.issues)
    assert all(i.flags == [] for i in res.issues)


def test_wehingen_page_dates_are_exact():
    res = parse_publication_page(read(SITE / "kiosk_mitteilungsblaetter_amtsblatt-wehingen.html"),
                                 f"{BASE}/amtsblatt-wehingen", today=TODAY)
    by_no = {i.issue_no: i.published_on for i in res.issues}
    assert len(by_no) == 12
    assert by_no[30] == date(2026, 7, 22) and by_no[19] == date(2026, 5, 6)


def test_bad_pages_are_reported_not_loaded():
    html = read(EDGE / "kiosk_mitteilungsblaetter_amtsblatt-musterstadt.html")
    res = parse_publication_page(html, f"{BASE}/amtsblatt-musterstadt", today=TODAY)

    assert [(i.issue_no, i.access_level) for i in res.issues] == [(10, "free"), (11, "paywalled"), (20, "free")]
    codes = sorted(p.code for p in res.problems)
    assert codes == ["bad_publication_date"] * 3 + ["duplicate_issue_in_page", "publication_date_in_future"]
    assert all(p.severity == "error" for p in res.problems if p.code != "duplicate_issue_in_page")


def test_footer_text_does_not_turn_a_free_issue_into_paywalled():
    html = read(EDGE / "kiosk_mitteilungsblaetter_amtsblatt-musterstadt.html")
    last = parse_publication_page(html, f"{BASE}/amtsblatt-musterstadt", today=TODAY).issues[-1]
    assert (last.issue_no, last.access_level) == (20, "free")


def test_calendar_week_mismatch_is_flagged_not_dropped():
    html = read(EDGE / "kiosk_mitteilungsblaetter_amtsblatt-musterstadt.html")
    issues = {i.issue_no: i for i in parse_publication_page(html, f"{BASE}/x", today=TODAY).issues}
    assert issues[20].flags == ["issue_number_vs_calendar_week_mismatch"]
    assert issues[10].flags == []


def test_missing_title_is_an_error():
    res = parse_publication_page(read(EDGE / "kiosk_mitteilungsblaetter_no-title.html"), f"{BASE}/x", today=TODAY)
    assert res.issues == [] and [p.code for p in res.problems] == ["missing_title"]


def test_page_without_issues():
    res = parse_publication_page(read(EDGE / "kiosk_mitteilungsblaetter_no-issues.html"), f"{BASE}/x", today=TODAY)
    assert res.title == "Amtsblatt Leerhausen"
    assert [p.code for p in res.problems] == ["no_issues_found"]


def test_german_dates():
    assert parse_german_date("5", "März", "2026") == date(2026, 3, 5)
    assert parse_german_date("5", "Maerz", "2026") == date(2026, 3, 5)
    assert parse_german_date("29", "Februar", "2025") is None  # not a leap year
    assert parse_german_date("1", "Foo", "2026") is None
