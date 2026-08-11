"""Build the daily HTML email digest and the full GitHub Pages board.

Layout: one section per region (NYC → Hudson Valley → Sullivan County
Catskills → Nearby & unplaced), each ordered by sale date (soonest first,
undated last). Email mode caps each region — Gmail clips messages over
~100KB — and links every truncation to the full board. Board mode renders
everything and gives every sale card a stable anchor id, so a specific sale
can be linked directly (…/#sale-craigslist-771234).
"""

from __future__ import annotations

import html
from datetime import date

from . import dates
from .classify import (ANTIQUE_EVENT, AUCTION, CATSKILLS, ESTATE_SALE,
                       HUDSON_VALLEY, NEARBY, NYC, TAG_SALE, UNCERTAIN,
                       UNKNOWN)
from .models import Sale, SourceHealth

_TYPE_BADGES = {
    ESTATE_SALE: ("ESTATE SALE", "#7a3fa0"),
    AUCTION: ("AUCTION", "#b06000"),
    ANTIQUE_EVENT: ("ANTIQUE SHOW / MARKET", "#0a7a2f"),
    TAG_SALE: ("TAG / YARD SALE", "#3d5a80"),
    UNCERTAIN: ("SALE — CHECK AD", "#555555"),
}

_STATUS_COLORS = {"TODAY": "#c8102e", "ON NOW": "#c8102e",
                  "THIS WEEKEND": "#0a5aa6"}

# (region keys, section anchor id, display title)
_REGIONS = [
    ((NYC,), "new-york-city", "🗽 New York City"),
    ((HUDSON_VALLEY,), "hudson-valley", "🏞️ Hudson Valley"),
    ((CATSKILLS,), "sullivan-catskills",
     "🎣 Sullivan County Catskills & Upper Delaware"),
    ((NEARBY, UNKNOWN, ""), "nearby", "📍 Nearby & unplaced"),
]

EMAIL_CAP_PER_REGION = 12


def _esc(s: str) -> str:
    return html.escape(s or "")


def _sort_key(s: Sale):
    return (0 if s.start_date else 1, s.start_date or "9999", -s.score)


def _visible(s: Sale, today: date) -> bool:
    """Hide sales that already ended; keep undated ones."""
    return dates.status(s.start_date, s.end_date, today) != "PAST"


def _chip(text: str, color: str) -> str:
    return (f'<span style="background:{color};color:#fff;padding:2px 7px;'
            f'border-radius:3px;font-size:11px;font-weight:bold;">{text}</span>')


def _card(s: Sale, is_new: bool, *, full: bool, board_url: str,
          today: date) -> str:
    badge_text, badge_color = _TYPE_BADGES.get(s.sale_type, ("", "#555"))
    chips = [_chip("NEW", "#c8102e")] if is_new else []
    chips.append(_chip(badge_text, badge_color))
    st = dates.status(s.start_date, s.end_date, today)
    if st in _STATUS_COLORS:
        chips.append(_chip(st, _STATUS_COLORS[st]))
    if s.is_online:
        chips.append(_chip("ONLINE BIDDING", "#666"))

    date_line = dates.display(s.start_date, s.end_date) or s.dates_text
    date_html = (f'<div style="font-size:13px;font-weight:bold;color:#0a7a2f;'
                 f'margin-top:5px;">📅 {_esc(date_line)}</div>' if date_line else
                 '<div style="font-size:12px;color:#999;margin-top:5px;">'
                 '📅 dates not detected — check the listing</div>')

    meta = " · ".join(filter(None, [_esc(s.location), _esc(s.source)]))
    tags = ("".join(f'<span style="background:#eee;color:#444;padding:1px 6px;'
                    f'border-radius:8px;font-size:11px;margin-right:4px;">'
                    f'{_esc(t)}</span>' for t in s.tags[:8]))
    tags_html = (f'<div style="margin-top:5px;">{tags}</div>' if tags else "")
    desc = (f'<div style="color:#666;font-size:12px;margin-top:4px;">'
            f'{_esc(s.description[:300])}</div>' if s.description else "")

    anchor = s.anchor()
    if full:
        share = (f'<a href="#{anchor}" title="Link directly to this sale" '
                 f'style="color:#999;text-decoration:none;">🔗 anchor</a>')
        open_div = f'<div id="{anchor}" class="sale-card" style="'
    else:
        share = (f'<a href="{_esc(board_url)}#{anchor}" title="Shareable link '
                 f'on the board" style="color:#999;text-decoration:none;">'
                 f'🔗 share</a>' if board_url else "")
        open_div = '<div style="'
    return f"""
    {open_div}border:1px solid #ddd;border-radius:6px;padding:12px 14px;margin:0 0 10px 0;">
      <div style="margin-bottom:4px;">{' '.join(chips)}</div>
      <a href="{_esc(s.url)}" style="font-size:15px;font-weight:bold;color:#0a5aa6;
         text-decoration:none;">{_esc(s.title)}</a>
      {date_html}
      <div style="color:#333;font-size:13px;margin-top:3px;">{meta}</div>
      {tags_html}
      <div style="color:#444;font-size:12px;margin-top:5px;font-style:italic;">{_esc(s.type_note)}</div>
      {desc}
      <div style="margin-top:6px;font-size:12px;"><a href="{_esc(s.url)}">Direct link →</a>
        &nbsp; {share}</div>
    </div>"""


def _health_rows(health: list[SourceHealth]) -> str:
    rows = []
    for h in health:
        dot = "🟢" if h.ok else "🔴"
        rows.append(f"<tr><td style='padding:3px 10px 3px 0;'>{dot} {_esc(h.source)}</td>"
                    f"<td style='padding:3px 10px 3px 0;text-align:right;'>{h.found}</td>"
                    f"<td style='padding:3px 0;color:#777;'>{_esc(h.note)}</td></tr>")
    return "\n".join(rows)


def _more(n: int, board_url: str, section_id: str) -> str:
    if n <= 0:
        return ""
    link = (f' <a href="{html.escape(board_url)}#{section_id}">'
            f'See all on the full board →</a>' if board_url else "")
    return f'<p style="color:#777;font-size:12px;">…and {n} more in this region.{link}</p>'


def build(new: list[Sale], seen: list[Sale], health: list[SourceHealth], *,
          full: bool = False, board_url: str = "",
          today: date | None = None) -> str:
    today = today or date.today()
    new_ids = {s.id for s in new}
    visible = [s for s in new + seen if _visible(s, today)]

    weekend = sum(1 for s in visible
                  if dates.status(s.start_date, s.end_date, today)
                  in ("TODAY", "ON NOW", "THIS WEEKEND"))
    if new:
        headline = (f"{len(new)} new sale{'s' if len(new) != 1 else ''} found "
                    f"today · {weekend} happening now or this weekend")
    else:
        headline = (f"No new sales today — {len(visible)} upcoming sales "
                    f"tracked · {weekend} happening now or this weekend")

    sections = []
    nav_items = []
    for region_keys, section_id, title in _REGIONS:
        group = sorted((s for s in visible if s.region in region_keys),
                       key=_sort_key)
        n_new = sum(1 for s in group if s.id in new_ids)
        nav_items.append(f'<a href="#{section_id}">{title.split(" ", 1)[1]}'
                         f' ({len(group)})</a>')
        cap = len(group) if full else EMAIL_CAP_PER_REGION
        cards = "".join(_card(s, s.id in new_ids, full=full,
                              board_url=board_url, today=today)
                        for s in group[:cap])
        if not cards:
            cards = ('<p style="color:#777;">No upcoming sales tracked here '
                     'right now.</p>')
        more = _more(len(group) - cap, board_url, section_id)
        sections.append(f"""
  <h2 id="{section_id}" style="font-size:17px;margin-top:26px;border-bottom:2px solid #eee;
      padding-bottom:4px;">{title}
    <span style="font-weight:normal;color:#777;font-size:13px;">({len(group)}
    upcoming{f", {n_new} new" if n_new else ""})</span></h2>
  {cards}{more}""")

    body = f"""
  <h1 style="font-size:20px;border-bottom:3px solid #7a3fa0;padding-bottom:8px;">
    🏺 Antiques &amp; Estate Sale Scan — {today.strftime("%A, %B ")}{today.day}, {today.year}{" · full board" if full else ""}</h1>
  <p style="font-size:14px;"><b>{headline}.</b>
  Estate sales, auctions, antique shows &amp; markets, and tag/yard/barn sales
  across NYC, the Hudson Valley, and the Sullivan County Catskills, ordered by
  date within each region.
  {f'<a href="{html.escape(board_url)}" style="font-size:13px;">Browse every tracked sale on the full board →</a>' if board_url and not full else ''}</p>

  {''.join(sections)}

  <h2 style="font-size:16px;margin-top:26px;">🩺 Source health</h2>
  <table style="font-size:13px;border-collapse:collapse;">{_health_rows(health)}</table>
  <p style="font-size:11px;color:#999;border-top:1px solid #eee;padding-top:8px;
     margin-top:14px;">
    Automated daily scan · Craigslist, EstateSales.NET, estatesales.org, gsalr,
    AuctionZip, AuctionNinja, HiBid, MaxSold, web discovery · repo: antiques</p>"""

    if not full:
        return (f'<div style="font-family:Arial,Helvetica,sans-serif;'
                f'max-width:680px;margin:auto;color:#222;">{body}</div>')

    nav = " · ".join(nav_items)
    # Standalone board page: sticky region nav + :target highlight so a
    # shared anchor link visibly lands on its sale card.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Antiques &amp; Estate Sale Board — NYC · Hudson Valley · Catskills</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #222; margin: 0;
         background: #fafafa; }}
  .wrap {{ max-width: 720px; margin: auto; padding: 12px 16px 40px; }}
  .nav {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd;
          padding: 10px 16px; font-size: 13px; z-index: 5; }}
  .nav a {{ color: #0a5aa6; text-decoration: none; margin-right: 4px; }}
  .sale-card {{ background: #fff; scroll-margin-top: 60px; }}
  .sale-card:target {{ border-color: #7a3fa0; box-shadow: 0 0 0 3px #e7d7f5; }}
  h2 {{ scroll-margin-top: 60px; }}
</style>
</head>
<body>
<div class="nav">{nav}</div>
<div class="wrap">{body}</div>
</body>
</html>"""


def subject(new: list[Sale], today: date | None = None) -> str:
    today = today or date.today()
    d = today.strftime("%b ") + str(today.day)
    if not new:
        return f"Sale Scan {d}: no new sales — see board for upcoming"
    estates = sum(1 for s in new if s.sale_type == ESTATE_SALE)
    auctions = sum(1 for s in new if s.sale_type == AUCTION)
    parts = []
    if estates:
        parts.append(f"{estates} estate")
    if auctions:
        parts.append(f"{auctions} auction{'s' if auctions != 1 else ''}")
    tag = f" ({', '.join(parts)})" if parts else ""
    top = max(new, key=lambda s: ((1 if s.start_date else 0), s.score))
    return (f"Sale Scan {d}: {len(new)} new sale{'s' if len(new) != 1 else ''}"
            f"{tag} — {top.title[:60]}")
