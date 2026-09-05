"""Persistent seen-sale state, committed back to the repo by the workflow so
"new since yesterday" survives between daily runs. Sales expire from state
quickly — they're ephemeral events, unlike durable classified listings."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

STATE_PATH = os.path.join("data", "seen_sales.json")
EXPIRE_DAYS = 60  # forget sales not seen for this long


def load() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(state: dict) -> None:
    cutoff = (date.today() - timedelta(days=EXPIRE_DAYS)).isoformat()
    state = {k: v for k, v in state.items() if v.get("last_seen", "") >= cutoff}
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


def mark(state: dict, sales: list) -> tuple[list, list]:
    """Update state with today's sales; return (new, previously_seen).

    Parsed sale dates are persisted in state and restored onto seen sales —
    detail pages (Craigslist) are only fetched the first time a listing is
    seen, so without this the PAST filter would stop working on day two.
    """
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    new, seen = [], []
    for s in sales:
        entry = state.get(s.id)
        if entry is None:
            state[s.id] = {"first_seen": today, "last_seen": today,
                           "title": s.title, "url": s.url,
                           "start": s.start_date, "end": s.end_date,
                           "recorded_at": now}
            if s.details_fetched:
                state[s.id]["dates_checked"] = True
            s.first_seen = today
            new.append(s)
        else:
            entry["last_seen"] = today
            if s.details_fetched:
                entry["dates_checked"] = True
            if s.start_date:
                entry["start"], entry["end"] = s.start_date, s.end_date
            elif entry.get("start"):
                s.start_date = entry["start"]
                s.end_date = entry.get("end") or entry["start"]
            s.first_seen = entry.get("first_seen", today)
            seen.append(s)
    return new, seen
