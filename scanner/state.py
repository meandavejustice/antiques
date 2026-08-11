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
    """Update state with today's sales; return (new, previously_seen)."""
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    new, seen = [], []
    for s in sales:
        entry = state.get(s.id)
        if entry is None:
            state[s.id] = {"first_seen": today, "last_seen": today,
                           "title": s.title, "url": s.url, "recorded_at": now}
            new.append(s)
        else:
            entry["last_seen"] = today
            seen.append(s)
    return new, seen
