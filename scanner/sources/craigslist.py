"""Craigslist source.

Sweeps the NY-area subdomains' garage-&-moving-sales and antiques
categories, plus a few free-text queries. The search pages are JS-rendered,
but Craigslist serves a static SEO fallback (`li.cl-static-search-result`)
that carries title, link, and location — enough for the digest, and the
link goes straight to the full ad.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..models import Sale, SourceHealth
from . import http

SOURCE = "Craigslist"

# Which region a subdomain implies when the ad text doesn't say.
_SUBDOMAIN_REGION = {
    "newyork": "NYC",
    "hudsonvalley": "HUDSON_VALLEY",
    "catskills": "CATSKILLS",
    "poconos": "CATSKILLS",   # PA side of the Upper Delaware
    "albany": "NEARBY",
    "longisland": "NEARBY",
    "newjersey": "NEARBY",
}


def _parse(html: str, city: str) -> list[Sale]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li.cl-static-search-result"):
        a = li.find("a", href=True)
        title_el = li.select_one("div.title") or a
        if not a or not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title:
            continue
        price_el = li.select_one("div.price")
        loc_el = li.select_one("div.location")
        url = a["href"]
        out.append(Sale(
            id=f"craigslist:{url.rstrip('/').rsplit('/', 1)[-1]}",
            source=SOURCE, title=title, url=url,
            location=(loc_el.get_text(strip=True) if loc_el else ""),
            description=(price_el.get_text(strip=True) if price_el else ""),
            region_hint=_SUBDOMAIN_REGION.get(city, ""),
        ))
    return out


def scan(config: dict) -> tuple[list[Sale], SourceHealth]:
    subdomains = config.get("subdomains", [])
    paths = config.get("paths", [])
    queries = config.get("queries", [])
    out: dict[str, Sale] = {}
    errors = total = 0
    for city in subdomains:
        urls = [f"https://{city}.craigslist.org/{p.strip('/')}" for p in paths]
        urls += [f"https://{city}.craigslist.org/search/sss?query={quote_plus(q)}"
                 for q in queries]
        for url in urls:
            total += 1
            try:
                resp = http.get(url, delay=0.6)
                for s in _parse(resp.text, city):
                    out.setdefault(s.id, s)
            except Exception:
                errors += 1
    ok = errors < total if total else False
    note = (f"{len(subdomains)} subdomains × {len(paths)} categories + "
            f"{len(queries)} queries"
            + (f", {errors}/{total} requests failed" if errors else ""))
    return list(out.values()), SourceHealth(SOURCE, ok, len(out), note)
