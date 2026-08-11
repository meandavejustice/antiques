"""Daily sale-scan orchestrator.

Runs every source (a failing source never kills the run), filters and
classifies candidates, parses sale dates, diffs against the persistent
seen-state, writes digest.html + the docs/ board, and emails the digest.
"""

from __future__ import annotations

import os
import sys

import yaml

from . import classify, dates, digest, emailer, state
from .models import Sale
from .sources import craigslist, discovery, sale_sites


def run() -> int:
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    sales: dict[str, Sale] = {}
    health = []

    print("Scanning Craigslist subdomains…")
    found, h = craigslist.scan(config.get("craigslist", {}))
    health.append(h)
    for s in found:
        sales.setdefault(s.id, s)

    print("Scanning sale-listing sites…")
    found, hs = sale_sites.scan(config.get("sale_sites", []))
    health.extend(hs)
    for s in found:
        sales.setdefault(s.id, s)

    print("Web discovery…")
    found, h = discovery.scan(config.get("discovery", {}))
    health.append(h)
    for s in found:
        sales.setdefault(s.id, s)

    relevant = [classify.classify(s) for s in sales.values()
                if classify.is_relevant(s)]
    for s in relevant:
        dates.enrich(s)
    print(f"{len(sales)} raw results → {len(relevant)} relevant after filtering")

    st = state.load()
    new, seen = state.mark(st, relevant)
    state.save(st)
    print(f"{len(new)} new, {len(seen)} previously seen")

    board_url = config.get("board_url", "")
    html_body = digest.build(new, seen, health, board_url=board_url)
    subj = digest.subject(new)
    with open("digest.html", "w") as f:
        f.write(html_body)
    # Full uncapped board with per-sale anchors, published via GitHub Pages.
    os.makedirs("docs", exist_ok=True)
    with open(os.path.join("docs", "index.html"), "w") as f:
        f.write(digest.build(new, seen, health, full=True, board_url=board_url))
    print(f"Digest written to digest.html — subject: {subj}")

    recipient = config.get("recipient", "")
    if emailer.configured():
        to = emailer.send(subj, html_body, recipient)
        print(f"Digest emailed to {to}")
    else:
        print("SMTP not configured (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD) — "
              "digest NOT emailed. See README for secret setup.")

    for h in (h for h in health if not h.ok):
        print(f"Source problem — {h.source}: {h.note}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
