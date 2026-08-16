"""Generic scraper for sale-listing sites (EstateSales.NET, estatesales.org,
gsalr, AuctionZip, AuctionNinja, HiBid, MaxSold, show calendars…).

These sites run on wildly different stacks, so rather than one brittle
parser per site, each site lists candidate URLs in config.yaml and we try
two extraction strategies per page:

1. schema.org JSON-LD — many sale/auction/event sites embed
   `<script type="application/ld+json">` Event objects carrying name, url,
   startDate/endDate, and a structured address. Best-quality data.
2. Keyword anchor harvest — any link whose text looks like a sale event
   (estate sale, auction, tag sale, antique show, …). The surrounding
   block's text is captured so the date parser and region matcher can work
   on addresses/dates printed next to the link.

Low-tech, but resilient to redesigns — and the digest's health table shows
which sites answered.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Sale, SourceHealth
from . import http

_SALE_TEXT_RE = re.compile(
    r"estate\s+sale|estate\s+auction|estate\s+liquidation|auction|tag\s+sale|"
    r"yard\s+sale|garage\s+sale|barn\s+sale|moving\s+sale|rummage|"
    r"antique|vintage\s+(?:market|fair|show|pop)|flea\s+market|"
    r"downsizing|whole\s+house|contents\s+of", re.I)

_SKIP_HREF = re.compile(
    r"(/cart|/account|/login|/signin|/register|/about|/contact|/privacy|"
    r"/terms|/faq|/blog/?$|/companies|/hire|#|mailto:|tel:|javascript:)", re.I)

_WS_RE = re.compile(r"\s+")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())[:24]


# ------------------------------------------------------------- JSON-LD ------
def _ld_objects(node) -> list[dict]:
    """Flatten a JSON-LD document (lists, @graph) into candidate objects."""
    if isinstance(node, list):
        return [o for n in node for o in _ld_objects(n)]
    if isinstance(node, dict):
        out = [node]
        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                out.extend(_ld_objects(node[key]))
        return out
    return []


def _ld_location(loc) -> str:
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if isinstance(loc, str):
        return loc
    if not isinstance(loc, dict):
        return ""
    parts = [loc.get("name", "")]
    addr = loc.get("address", {})
    if isinstance(addr, str):
        parts.append(addr)
    elif isinstance(addr, dict):
        parts += [addr.get("streetAddress", ""), addr.get("addressLocality", ""),
                  addr.get("addressRegion", ""), addr.get("postalCode", "")]
    return _WS_RE.sub(" ", ", ".join(p for p in parts if p)).strip()


def _from_jsonld(soup: BeautifulSoup, base_url: str, site: str,
                 hint: str) -> list[Sale]:
    from .. import dates
    out: dict[str, Sale] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            doc = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _ld_objects(doc):
            t = obj.get("@type", "")
            types = {t} if isinstance(t, str) else set(t or [])
            if not types & {"Event", "SaleEvent", "Sale", "SocialEvent",
                            "ExhibitionEvent", "Festival"}:
                continue
            name = _WS_RE.sub(" ", str(obj.get("name", ""))).strip()
            url = obj.get("url", "") or base_url
            if not name:
                continue
            url = urljoin(base_url, url)
            s = Sale(
                id=f"{_slug(site)}:{url}",
                source=site, title=name[:200], url=url,
                location=_ld_location(obj.get("location", "")),
                description=_WS_RE.sub(
                    " ", str(obj.get("description", "")))[:400],
                image=(obj.get("image", "") if isinstance(obj.get("image"), str)
                       else ""),
                start_date=dates.parse_iso(str(obj.get("startDate", ""))),
                end_date=dates.parse_iso(str(obj.get("endDate", ""))),
                region_hint=hint,
            )
            out.setdefault(s.id, s)
    return list(out.values())


# ------------------------------------------------------ anchor harvest ------
def _from_anchors(soup: BeautifulSoup, base_url: str, site: str,
                  hint: str) -> list[Sale]:
    out: dict[str, Sale] = {}
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 8 or len(text) > 250:
            continue
        if not _SALE_TEXT_RE.search(text):
            continue
        href = a["href"]
        if _SKIP_HREF.search(href):
            continue
        url = urljoin(base_url, href)
        if not url.startswith("http"):
            continue
        # Climb to a card-sized block: sale cards print the dates and
        # address *near* the link, not in it. Stop before page-level
        # containers so context stays card-sized.
        parent = a.parent
        for _ in range(4):
            if (parent is None or parent.parent is None
                    or parent.parent.name in ("body", "html", "main", "ul",
                                              "ol", "table", "section")
                    or len(parent.get_text(strip=True)) >= 200
                    or len(parent.parent.get_text(strip=True)) > 700):
                break
            parent = parent.parent
        context = _WS_RE.sub(" ", parent.get_text(" ", strip=True))[:500] \
            if parent else ""
        lid = f"{_slug(site)}:{url}"
        if lid not in out:
            out[lid] = Sale(id=lid, source=site, title=text[:200], url=url,
                            description=context, region_hint=hint)
    return list(out.values())


def scan(sites: list[dict]) -> tuple[list[Sale], list[SourceHealth]]:
    sales: dict[str, Sale] = {}
    health: list[SourceHealth] = []
    for site in sites:
        name = site["name"]
        hint = site.get("region_hint", "")
        found: dict[str, Sale] = {}
        last_err = ""
        reached = False
        for url in site.get("urls", []):
            try:
                resp = http.get(url, delay=1.5)
                reached = True
                soup = BeautifulSoup(resp.text, "html.parser")
                for s in _from_jsonld(soup, url, name, hint):
                    found.setdefault(s.id, s)
                for s in _from_anchors(soup, url, name, hint):
                    found.setdefault(s.id, s)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
        sales.update(found)
        if reached:
            health.append(SourceHealth(
                name, True, len(found),
                "no sale links found on page (JS-only site?)" if not found else ""))
        else:
            health.append(SourceHealth(name, False, 0, last_err or "unreachable"))
    return list(sales.values()), health
