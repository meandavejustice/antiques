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


def fetch_details(sales: list[Sale], state: dict, *,
                  limit: int = 150) -> SourceHealth:
    """Fetch the ad page for Craigslist sales not yet detail-checked.

    The static search results carry no dates — the sale dates live on the
    ad itself (the gms category's "sale dates" attribute and/or the post
    body). Each ad is fetched once ever: the parsed dates and a
    dates_checked flag are cached in the seen-state, so the steady-state
    daily cost is roughly one request per brand-new ad (the cap spreads a
    backlog across runs). Also picks up the address and body text, which
    sharpens region matching and item tags.
    """
    pending = [s for s in sales if s.source == SOURCE
               and not state.get(s.id, {}).get("dates_checked")]
    todo = pending[:limit]
    fetched = errors = 0
    for s in todo:
        try:
            resp = http.get(s.url, delay=0.5)
            soup = BeautifulSoup(resp.text, "html.parser")
            attrs = " ".join(g.get_text(" ", strip=True)
                             for g in soup.select("p.attrgroup, div.attrgroup"))
            body_el = soup.select_one("#postingbody")
            body = (body_el.get_text(" ", strip=True)
                    .replace("QR Code Link to This Post", "").strip()
                    if body_el else "")
            addr_el = soup.select_one(".mapaddress")
            if addr_el:
                s.location = addr_el.get_text(" ", strip=True)
            s.description = " · ".join(filter(None, [attrs[:200], body]))[:500]
            s.details_fetched = True
            fetched += 1
        except Exception:
            errors += 1
    skipped = len(pending) - len(todo)
    note = (f"{fetched}/{len(todo)} new ad pages fetched for dates"
            + (f", {skipped} deferred to tomorrow (cap {limit})" if skipped > 0 else "")
            + (f", {errors} failed" if errors else ""))
    return SourceHealth("Craigslist ad details", errors == 0 or fetched > 0,
                        fetched, note)


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
