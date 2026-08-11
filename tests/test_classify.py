"""Classifier + date-parser regression tests: `python tests/test_classify.py`."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scanner import classify, dates  # noqa: E402
from scanner.models import Sale  # noqa: E402

TODAY = date(2026, 8, 11)  # a fixed Tuesday, so weekend logic is deterministic


def mk(title, desc="", loc="", hint=""):
    return Sale(id="t", source="test", title=title, url="u",
                description=desc, location=loc, region_hint=hint)


def check(title, desc, relevant, sale_type=None, region=None, loc="", hint=""):
    s = mk(title, desc, loc, hint)
    got_rel = classify.is_relevant(s)
    assert got_rel == relevant, f"{title!r}: relevance {got_rel} != {relevant}"
    if not relevant:
        return None
    classify.classify(s)
    if sale_type is not None:
        assert s.sale_type == sale_type, \
            f"{title!r}: type {s.sale_type} != {sale_type}"
    if region is not None:
        assert s.region == region, f"{title!r}: region {s.region} != {region}"
    return s


# ------------------------------------------------------------- relevance ----
# The classic false-positive traps: real-estate ads contain "estate sale…".
check("Real estate sale — 3BR colonial in Monticello", "", False)
check("Real Estate Agent serving the Hudson Valley", "", False)
check("WANTED: we buy estates, antiques, gold — cash paid", "", False)
check("Estate cleanout service — junk removal, we haul", "", False)
check("Now hiring: estate sale staff", "", False)
check("Open house Sunday — beautiful Rhinebeck farmhouse", "", False)
check("Antique dresser $200", "", False)  # single item, not a sale event

# The events we want.
check("HUGE Estate Sale — everything must go!", "50 years of antiques",
      True, classify.ESTATE_SALE)
check("Estate liquidation this weekend", "", True, classify.ESTATE_SALE)
check("Antique auction Saturday at the fairgrounds", "",
      True, classify.AUCTION)
check("Multi-family yard sale", "", True, classify.TAG_SALE)
check("Barn sale — primitives, crocks, farmhouse tables", "",
      True, classify.TAG_SALE)
check("Annual Antiques Fair on the green", "", True, classify.ANTIQUE_EVENT)
check("Flea market every Sunday", "", True, classify.ANTIQUE_EVENT)
check("Vintage pop-up market", "", True, classify.ANTIQUE_EVENT)
check("Stoop sale in Park Slope", "", True, classify.TAG_SALE)

# Estate auctions rank as auctions; online-only flag.
s = check("Estate auction — online only, bidding ends Aug 20", "",
          True, classify.AUCTION)
assert s.is_online, "online-only auction not flagged"

# --------------------------------------------------------------- regions ----
check("Estate sale", "", True, None, classify.NYC, loc="Brooklyn, NY")
check("Estate sale in Astoria this weekend", "", True, None, classify.NYC)
check("Tag sale", "", True, None, classify.HUDSON_VALLEY,
      loc="Kingston, NY 12401")
check("Estate sale", "full house in Rhinebeck NY", True, None,
      classify.HUDSON_VALLEY)
check("Barn sale", "", True, None, classify.CATSKILLS,
      loc="Livingston Manor, NY")
check("Estate sale", "contents of Monticello NY home", True, None,
      classify.CATSKILLS)
check("Estate auction", "Sullivan County estate — antiques, tools", True,
      None, classify.CATSKILLS)
# Upper Delaware PA side counts as Catskills.
check("Estate sale", "", True, None, classify.CATSKILLS, loc="Honesdale, PA")
# Zip prefixes: Sullivan is 127xx, Manhattan 100xx.
check("Estate sale", "", True, None, classify.CATSKILLS,
      loc="Somewhere, NY 12701")
check("Estate sale", "", True, None, classify.NYC, loc="New York, NY 10011")
# Zips in prose need a state prefix; "10000 sq ft" must NOT read as a zip.
check("Estate sale in a 10000 sq ft warehouse", "", True, None,
      classify.CATSKILLS, hint="CATSKILLS")
# Region hint fallback (e.g. found via the catskills craigslist subdomain).
check("Moving sale everything must go", "", True, None, classify.CATSKILLS,
      hint="CATSKILLS")
check("Moving sale everything must go", "", True, None, classify.UNKNOWN)
# "Queen Anne" furniture must not match Queens.
s = mk("Estate sale — Queen Anne furniture", "", "Nyack, NY")
classify.classify(s)
assert s.region == classify.HUDSON_VALLEY, f"queen anne trap: {s.region}"
# Colonial Williamsburg reproductions must not map anywhere.
check("Estate sale — Colonial Williamsburg reproductions", "", True, None,
      classify.UNKNOWN)
check("Estate sale", "", True, None, classify.NEARBY, loc="Ridgewood, NJ 07450")

# ------------------------------------------------------------------ tags ----
s = mk("Estate sale", "mid-century teak credenza, records and LPs, "
       "sterling flatware, oil paintings", "Beacon, NY")
classify.classify(s)
for expected in ("mid-century", "vinyl & audio", "silver", "art"):
    assert expected in s.tags, f"missing tag {expected}: {s.tags}"
s2 = mk("Yard sale", "start early, quart jars, smart TVs", "")
classify.classify(s2)
assert "art" not in s2.tags, f"'art' word-boundary broken: {s2.tags}"

# ----------------------------------------------------------- date parser ----
def d(text, start, end):
    got = dates.parse(text, TODAY)
    assert got == (start, end), f"{text!r}: {got} != {(start, end)}"

d("Sale Aug 15", "2026-08-15", "2026-08-15")
d("August 15-17", "2026-08-15", "2026-08-17")
d("Aug 30 - Sep 1", "2026-08-30", "2026-09-01")
d("Fri 8/15 to Sun 8/17", "2026-08-15", "2026-08-17")
d("8/15/26", "2026-08-15", "2026-08-15")
d("Sale on 2026-08-22", "2026-08-22", "2026-08-22")
d("starts Sept. 5th", "2026-09-05", "2026-09-05")
# Year inference: a January date seen in August means next January.
d("Antique show Jan 10", "2027-01-10", "2027-01-10")
# December→January ranges roll the year for the end date.
d("Dec 30 - Jan 2", "2026-12-30", "2027-01-02")
# Recently-past dates stay in the current year (grace window).
d("Sale was Aug 1", "2026-08-01", "2026-08-01")
d("no dates here at all", "", "")
d("open 9-4 both days", "", "")  # bare numbers must not parse as dates

assert dates.status("2026-08-11", "2026-08-11", TODAY) == "TODAY"
assert dates.status("2026-08-10", "2026-08-12", TODAY) == "ON NOW"
assert dates.status("2026-08-15", "2026-08-16", TODAY) == "THIS WEEKEND"
assert dates.status("2026-08-25", "2026-08-25", TODAY) == ""
assert dates.status("2026-08-01", "2026-08-02", TODAY) == "PAST"
assert dates.display("2026-08-15", "2026-08-16") == "Sat, Aug 15 – Sun, Aug 16"

# Anchor slugs are stable and URL-safe.
s = mk("Estate sale")
s.id = "craigslist:7712345678.html"
assert s.anchor() == "sale-craigslist-7712345678-html", s.anchor()

print("All classifier, region, tag, and date tests passed.")
