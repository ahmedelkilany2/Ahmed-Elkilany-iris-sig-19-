"""Polite HTTP: identifies itself, rate limits, retries, honours robots.txt."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    def __init__(self, code: str, url: str, detail: str = ""):
        super().__init__(f"{code}: {url} {detail}".strip())
        self.code = code
        self.url = url
        self.detail = detail


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    history: list[str] = field(default_factory=list)

    @property
    def redirected(self) -> bool:
        return bool(self.history)


class PoliteFetcher:
    def __init__(
        self,
        user_agent: str,
        min_delay: float = 2.0,
        timeout: float = 20.0,
        max_retries: int = 3,
        session: requests.Session | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.headers["Accept-Language"] = "de,en;q=0.5"
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    # -- rate limit -------------------------------------------------------
    @staticmethod
    def _origin(url: str) -> str:
        parts = urlparse(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _throttle(self, origin: str) -> None:
        """At least min_delay between requests to one host, or the host's Crawl-delay if that is larger."""
        delay = self._host_delay.get(origin, self.min_delay)
        last = self._last_request.get(origin)
        if last is not None:
            wait = delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[origin] = self._clock()

    # -- robots.txt -------------------------------------------------------
    def _robots_for(self, url: str) -> RobotFileParser | None:
        origin = self._origin(url)
        if origin in self._robots:
            return self._robots[origin]
        robots_url = origin + "/robots.txt"
        parser: RobotFileParser | None
        try:
            resp = self._request_with_retries(robots_url, allow_redirects=True)
        except FetchError:
            parser = None  # could not read it at all: be conservative
        else:
            if resp.status_code in (401, 403):
                parser = None  # access to robots.txt itself denied: treat as disallow
            elif 400 <= resp.status_code < 500:
                parser = RobotFileParser()
                parser.parse([])  # no robots.txt means no restrictions
            else:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                token = self.user_agent.split("/")[0].strip() or "*"
                crawl_delay = parser.crawl_delay(token)
                if crawl_delay:
                    self._host_delay[origin] = max(self.min_delay, float(crawl_delay))
        self._robots[origin] = parser
        return parser

    def sitemaps_for(self, url: str) -> list[str]:
        """Sitemap URLs declared in the robots.txt of url's host (empty if unreadable)."""
        parser = self._robots_for(url)
        return list(parser.site_maps() or []) if parser else []

    def allowed(self, url: str) -> bool:
        parser = self._robots_for(url)
        if parser is None:
            return False
        token = self.user_agent.split("/")[0].strip() or "*"
        return parser.can_fetch(token, url)

    # -- requests ---------------------------------------------------------
    def _request_with_retries(self, url: str, allow_redirects: bool = True) -> requests.Response:
        last_detail = ""
        origin = self._origin(url)
        for attempt in range(self.max_retries + 1):
            self._throttle(origin)
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=allow_redirects)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_detail = f"{type(exc).__name__}"
            else:
                if resp.status_code not in RETRY_STATUSES:
                    return resp
                last_detail = f"http {resp.status_code}"
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit() and attempt < self.max_retries:
                    self._sleep(min(int(retry_after), 60))
                    continue
            if attempt < self.max_retries:
                self._sleep(min(1.5 * 2**attempt, 30))
        raise FetchError("network_failure", url, f"gave up after {self.max_retries + 1} attempts ({last_detail})")

    def get(self, url: str, check_robots: bool = True, accept: str = "html") -> FetchResult:
        if check_robots and not self.allowed(url):
            raise FetchError("blocked_by_robots", url, "robots.txt disallows this path or could not be read")
        resp = self._request_with_retries(url)
        if resp.status_code >= 400:
            raise FetchError(f"http_{resp.status_code}", url)
        ctype = resp.headers.get("Content-Type", "")
        if ctype and accept not in ctype.lower():
            raise FetchError("unexpected_content_type", url, ctype)
        return FetchResult(
            url=url,
            final_url=resp.url,
            status=resp.status_code,
            text=resp.text,
            history=[r.url for r in resp.history],
        )


class FixtureFetcher:
    """Serves saved HTML from a directory so the whole pipeline runs offline.

    /kiosk/mitteilungsblaetter                  -> kiosk_mitteilungsblaetter.html
    /kiosk/mitteilungsblaetter/amtsblatt-xyz    -> kiosk_mitteilungsblaetter_amtsblatt-xyz.html
    /sitemap_archive.xml                        -> sitemap_archive.xml   (host is ignored)
    Sitemap lines come from a robots.txt file in the same directory, if there is one.
    """

    def __init__(self, root):
        from pathlib import Path

        self.root = Path(root)

    def sitemaps_for(self, url: str) -> list[str]:
        robots = self.root / "robots.txt"
        if not robots.is_file():
            return []
        return [ln.split(":", 1)[1].strip() for ln in robots.read_text(encoding="utf-8").splitlines()
                if ln.lower().startswith("sitemap:")]

    def get(self, url: str, check_robots: bool = True, accept: str = "html") -> FetchResult:
        raw = urlparse(url).path.strip("/").replace("/", "_")
        name = raw if raw.endswith(".xml") else raw + ".html"
        path = self.root / name
        if not path.is_file():
            raise FetchError("http_404", url, f"no fixture {name}")
        return FetchResult(url=url, final_url=url, status=200, text=path.read_text(encoding="utf-8"))
