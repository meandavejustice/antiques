"""Polite HTTP helper shared by all scrapers."""

from __future__ import annotations

import time

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})


def get(url: str, *, delay: float = 0.8, timeout: int = 25, **kwargs) -> requests.Response:
    """GET with a crawl delay and sane defaults. Raises on HTTP errors."""
    time.sleep(delay)
    resp = _session.get(url, timeout=timeout, **kwargs)
    resp.raise_for_status()
    return resp
