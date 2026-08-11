"""Shared data types for the sale scanner."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class Sale:
    id: str                      # stable dedupe key, e.g. "craigslist:7712345678"
    source: str                  # human-readable source name
    title: str
    url: str
    location: str = ""           # free-text place ("Monticello, NY 12701")
    description: str = ""        # any extra text captured (feeds the classifier)
    image: str = ""
    dates_text: str = ""         # date text as the source displayed it
    start_date: str = ""         # ISO yyyy-mm-dd once parsed
    end_date: str = ""
    region_hint: str = ""        # region implied by where it was found

    # Filled in by the classifier:
    sale_type: str = ""          # see classify.py type constants
    type_note: str = ""
    region: str = ""             # NYC / HUDSON_VALLEY / CATSKILLS / NEARBY / UNKNOWN
    tags: list[str] = field(default_factory=list)  # what kinds of things they have
    is_online: bool = False      # online-only auction (no in-person browsing)
    score: int = 0               # tiebreak sort key: higher = more promising

    def text(self) -> str:
        return f"{self.title} {self.location} {self.description}"

    def anchor(self) -> str:
        """Stable fragment id for direct links to this sale on the board."""
        slug = re.sub(r"[^a-z0-9]+", "-", self.id.lower()).strip("-")
        return f"sale-{slug[:90]}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceHealth:
    source: str
    ok: bool
    found: int = 0
    note: str = ""
