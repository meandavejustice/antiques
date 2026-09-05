"""Parse sale dates out of listing text.

Sources write dates every way imaginable — "Aug 15-17", "Sat 8/16",
"Friday, August 15th – Sunday, August 17th", "2026-08-15", "starts Aug. 15".
We extract the first recognizable date (or range) and normalize to ISO so
regions can be ordered by upcoming date. Sales with no recognizable date are
kept and sorted after dated ones.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_RE = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
             r"jun[e]?|jul[y]?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
             r"nov(?:ember)?|dec(?:ember)?)")
# Range separators may carry a weekday ("8/15 to Sun 8/17").
_WD = r"(?:(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?\.?,?\s+)?"
_DASH = rf"\s*(?:-|–|—|to|thru|through|&)\s*{_WD}"
_ORD = r"(?:st|nd|rd|th)?"

# "August 15" / "Aug. 15th - 17" / "Aug 15 - Sep 2" (optional year)
_WORDY_RE = re.compile(
    rf"\b{_MONTH_RE}\.?\s+(\d{{1,2}}){_ORD}(?:,?\s*(20\d\d))?"
    rf"(?:{_DASH}(?:{_MONTH_RE}\.?\s+)?(\d{{1,2}}){_ORD}(?:,?\s*(20\d\d))?)?",
    re.I)

# "8/15" / "8/15/26" / "8/15-8/17" / "8/15/2026 - 8/17/2026"
_SLASH_RE = re.compile(
    rf"\b(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{2,4}}))?"
    rf"(?:{_DASH}(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{2,4}}))?)?\b", re.I)

# ISO dates (JSON-LD startDate etc.), optional trailing time component.
_ISO_RE = re.compile(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})")


def _mk(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_year(month: int, day: int, today: date) -> date | None:
    """No year given: pick this year, or next if that's far in the past.

    45-day grace keeps just-ended sales parseable without dragging a
    January mention seen in August a year forward incorrectly.
    """
    d = _mk(today.year, month, day)
    if d is None:
        return None
    if d < today - timedelta(days=45):
        return _mk(today.year + 1, month, day)
    return d


def _year4(y: str | None, fallback: int) -> int | None:
    if not y:
        return None
    n = int(y)
    if n < 100:
        n += 2000
    return n if 2000 <= n <= fallback + 5 else None


def parse_iso(text: str) -> str:
    """First ISO date in `text`, normalized, or ''. For JSON-LD fields."""
    m = _ISO_RE.search(text or "")
    if not m:
        return ""
    d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return d.isoformat() if d else ""


def parse(text: str, today: date | None = None) -> tuple[str, str]:
    """Return (start_iso, end_iso) for the first date/range found, or ('','')."""
    today = today or date.today()
    if not text:
        return "", ""

    m = _ISO_RE.search(text)
    if m:
        start = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if start:
            m2 = _ISO_RE.search(text, m.end())
            end = (_mk(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                   if m2 else None)
            if end and start <= end <= start + timedelta(days=30):
                return start.isoformat(), end.isoformat()
            return start.isoformat(), start.isoformat()

    m = _WORDY_RE.search(text)
    if m:
        mon1, d1, y1, mon2, d2, y2 = m.groups()
        month1 = _MONTHS[mon1.lower()[:3]]
        year1 = _year4(y1, today.year)
        start = (_mk(year1, month1, int(d1)) if year1
                 else _infer_year(month1, int(d1), today))
        if start:
            if d2:
                month2 = _MONTHS[mon2.lower()[:3]] if mon2 else month1
                year2 = _year4(y2, today.year)
                end = (_mk(year2, month2, int(d2)) if year2
                       else _mk(start.year, month2, int(d2)))
                if end and end < start:      # "Dec 30 - Jan 2" rolls over
                    end = _mk(start.year + 1, month2, int(d2))
                if end and start <= end <= start + timedelta(days=45):
                    return start.isoformat(), end.isoformat()
            return start.isoformat(), start.isoformat()

    # Post bodies are noisy ("50/50 raffle", "open 9/making offers") — walk
    # the matches and take the first that is a real calendar date.
    for m in _SLASH_RE.finditer(text):
        mo1, d1, y1, mo2, d2, y2 = m.groups()
        mo1, d1 = int(mo1), int(d1)
        if not (1 <= mo1 <= 12):
            continue
        year1 = _year4(y1, today.year)
        start = _mk(year1, mo1, d1) if year1 else _infer_year(mo1, d1, today)
        if start:
            if mo2 and d2:
                mo2, d2 = int(mo2), int(d2)
                year2 = _year4(y2, today.year)
                end = (_mk(year2, mo2, d2) if year2
                       else _mk(start.year, mo2, d2)) if 1 <= mo2 <= 12 else None
                if end and end < start:
                    end = _mk(start.year + 1, mo2, d2)
                if end and start <= end <= start + timedelta(days=45):
                    return start.isoformat(), end.isoformat()
            return start.isoformat(), start.isoformat()

    return "", ""


def enrich(sale, today: date | None = None) -> None:
    """Fill sale.start_date/end_date from dates_text, then title+description."""
    if sale.start_date:                      # already set (JSON-LD etc.)
        if not sale.end_date:
            sale.end_date = sale.start_date
        return
    for text in (sale.dates_text, sale.title, sale.description):
        start, end = parse(text, today)
        if start:
            sale.start_date, sale.end_date = start, end
            return


def _fmt(d: date) -> str:
    return d.strftime("%a, %b ") + str(d.day)


def display(start_iso: str, end_iso: str) -> str:
    """Human date line: 'Sat, Aug 15' or 'Sat, Aug 15 – Sun, Aug 16'."""
    if not start_iso:
        return ""
    out = _fmt(date.fromisoformat(start_iso))
    if end_iso and end_iso != start_iso:
        out += " – " + _fmt(date.fromisoformat(end_iso))
    return out


def status(start_iso: str, end_iso: str, today: date | None = None) -> str:
    """'' / 'TODAY' / 'ON NOW' / 'THIS WEEKEND' / 'PAST' for badge chips."""
    if not start_iso:
        return ""
    today = today or date.today()
    s = date.fromisoformat(start_iso)
    e = date.fromisoformat(end_iso or start_iso)
    if e < today:
        return "PAST"
    if s <= today <= e:
        return "TODAY" if s == today else "ON NOW"
    saturday = today + timedelta(days=(5 - today.weekday()) % 7)
    sunday = saturday + timedelta(days=1)
    if s <= sunday and e >= saturday:
        return "THIS WEEKEND"
    return ""
