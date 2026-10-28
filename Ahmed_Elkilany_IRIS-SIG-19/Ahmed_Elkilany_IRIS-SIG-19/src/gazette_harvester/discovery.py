"""Find publication pages through the sitemaps that robots.txt points to.

NUSSBAUM.de declares its sitemaps in robots.txt. They are daily files per content type, and the
archive index lists `sitemap_publications_*.xml` files that contain the Kiosk publication pages.
Only those files are read (not the hundreds of news/event/obituary ones), which keeps the number of
requests small, because the site asks for a 10 second crawl delay.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from lxml import etree

from .http import FetchError
from .models import Problem
from .parse import PUBLICATION_PATH_RE

MAX_CHILD_SITEMAPS = 20
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")
_SAFE_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


class SitemapError(ValueError):
    pass


def parse_sitemap(text: str) -> tuple[str, list[str]]:
    """Return ('index' | 'urlset', [loc, ...]). Entities are not expanded and nothing is fetched."""
    try:
        root = etree.fromstring(_XML_DECL.sub("", text).encode("utf-8"), _SAFE_PARSER)
    except etree.XMLSyntaxError as exc:
        raise SitemapError(f"not valid XML: {exc}") from exc
    kind = etree.QName(root).localname
    if kind not in ("sitemapindex", "urlset"):
        raise SitemapError(f"unexpected root element <{kind}>")
    locs = [(el.text or "").strip() for el in root.iter("{*}loc")]
    return ("index" if kind == "sitemapindex" else "urlset"), [loc for loc in locs if loc]


def _publication_urls(urls: list[str], host: str) -> list[str]:
    out = []
    for u in urls:
        parts = urlparse(u)
        m = PUBLICATION_PATH_RE.match(parts.path)
        if parts.netloc == host and m and m.group(1) != "undefined":
            out.append(u)
    return out


def discover_from_sitemaps(fetcher, index_url: str, problems: list[Problem],
                           max_children: int = MAX_CHILD_SITEMAPS) -> list[str]:
    host = urlparse(index_url).netloc
    found: list[str] = []
    for root_url in fetcher.sitemaps_for(index_url):
        try:
            kind, locs = parse_sitemap(fetcher.get(root_url, accept="xml").text)
        except FetchError as exc:
            problems.append(Problem(f"sitemap_{exc.code}", exc.detail or "could not read sitemap", root_url))
            continue
        except SitemapError as exc:
            problems.append(Problem("sitemap_malformed", str(exc), root_url))
            continue

        if kind == "urlset":
            found += _publication_urls(locs, host)
            continue

        children = [u for u in locs if "publications" in urlparse(u).path.rsplit("/", 1)[-1]]
        if len(children) > max_children:
            problems.append(Problem("sitemap_children_truncated",
                                    f"{len(children)} publication sitemaps listed, reading the first {max_children}", root_url))
            children = children[:max_children]
        for child in children:
            try:
                _, child_locs = parse_sitemap(fetcher.get(child, accept="xml").text)
            except FetchError as exc:
                problems.append(Problem(f"sitemap_{exc.code}", exc.detail or "could not read sitemap", child))
            except SitemapError as exc:
                problems.append(Problem("sitemap_malformed", str(exc), child))
            else:
                found += _publication_urls(child_locs, host)
    return list(dict.fromkeys(found))
