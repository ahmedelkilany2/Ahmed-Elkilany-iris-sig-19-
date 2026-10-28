"""Verify the endpoint named in the brief instead of assuming it still works."""
from __future__ import annotations

from urllib.parse import urlparse

from .http import FetchError


def probe_endpoint(fetcher, url: str) -> dict:
    finding = {"url": url}
    try:
        res = fetcher.get(url)
    except FetchError as exc:
        finding.update(verdict="unreachable_or_blocked", detail=str(exc))
        return finding

    start, end = urlparse(url), urlparse(res.final_url)
    finding.update(status=res.status, final_url=res.final_url, redirect_chain=res.history)
    moved = (start.netloc.removeprefix("www.") != end.netloc.removeprefix("www.")) or not end.path.startswith(start.path)
    if res.redirected and moved:
        finding.update(
            verdict="obsolete_redirect",
            detail=f"{start.netloc}{start.path} now redirects to {end.netloc}{end.path}",
        )
    else:
        finding.update(verdict="reachable", detail="served without leaving the original path")
    return finding
