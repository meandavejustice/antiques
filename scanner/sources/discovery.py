"""Wide-net web discovery.

Catches what the direct scrapers miss: estate-sale companies' own sites,
show promoters, local-paper event calendars, town pages. Two backends:

- Brave Search API when BRAVE_API_KEY is set (free tier: 2,000 queries/mo,
  the daily run uses ~8) — most robust.
- DuckDuckGo's static HTML endpoint otherwise — keyless, zero setup.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Sale, SourceHealth
from . import http

SOURCE = "Web discovery"


def _brave(queries: list[str], key: str) -> list[Sale]:
    import requests
    out: dict[str, Sale] = {}
    for q in queries:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": q, "count": 20, "country": "us"},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            timeout=25,
        )
        resp.raise_for_status()
        for item in resp.json().get("web", {}).get("results", []):
            url = item.get("url", "")
            sid = f"web:{url}"
            if url and sid not in out:
                out[sid] = Sale(
                    id=sid, source=SOURCE,
                    title=(item.get("title") or "")[:200], url=url,
                    description=(item.get("description") or "")[:400],
                )
    return list(out.values())


def _ddg_url(href: str) -> str:
    """DDG result hrefs are often redirect links carrying uddg=<real url>."""
    if "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def _duckduckgo(queries: list[str]) -> list[Sale]:
    out: dict[str, Sale] = {}
    for q in queries:
        resp = http.get(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}",
                        delay=2.0)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.result__a"):
            url = _ddg_url(a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not url.startswith("http") or not title:
                continue
            snippet_el = a.find_parent(class_="result__body")
            snippet = ""
            if snippet_el:
                sn = snippet_el.select_one(".result__snippet")
                snippet = sn.get_text(" ", strip=True)[:400] if sn else ""
            sid = f"web:{url}"
            if sid not in out:
                out[sid] = Sale(id=sid, source=SOURCE, title=title[:200],
                                url=url, description=snippet)
    return list(out.values())


def scan(config: dict) -> tuple[list[Sale], SourceHealth]:
    queries = config.get("queries", [])
    try:
        key = os.environ.get("BRAVE_API_KEY")
        if key:
            sales = _brave(queries, key)
            note = "via Brave Search API"
        else:
            sales = _duckduckgo(queries)
            note = "via DuckDuckGo (keyless; set BRAVE_API_KEY for the Brave API)"
        return sales, SourceHealth(SOURCE, True, len(sales), note)
    except Exception as e:
        return [], SourceHealth(SOURCE, False, 0, f"{type(e).__name__}: {e}")
