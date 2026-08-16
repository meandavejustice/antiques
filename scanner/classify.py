"""Classify sale listings: what kind of sale, where, and what they have.

Three jobs:
1. `is_relevant` — keep only actual sale *events* (estate/tag/yard/barn
   sales, auctions, antique shows & flea markets), dropping individual
   item ads, "we buy estates" service ads, real-estate listings, and job
   posts that the category sweeps drag in.
2. `classify` — assign a sale type, extract item-category tags (what kinds
   of things the sale advertises), flag online-only auctions, and score.
3. Region assignment — NYC / Hudson Valley / Sullivan County Catskills
   (incl. the PA side of the Upper Delaware) / Nearby, from place names and
   zip codes in the listing, falling back to the source's region hint.
"""

from __future__ import annotations

import re

from .models import Sale

# Sale types, in rough order of how promising they are for antique hunting.
ESTATE_SALE = "ESTATE_SALE"      # whole-house contents — the good stuff
AUCTION = "AUCTION"              # estate/antique auctions (in-person or online)
ANTIQUE_EVENT = "ANTIQUE_EVENT"  # antique shows, fairs, flea & vintage markets
TAG_SALE = "TAG_SALE"            # tag / yard / garage / barn / moving sales
UNCERTAIN = "UNCERTAIN"

_TYPE_RANK = {ESTATE_SALE: 5, ANTIQUE_EVENT: 4, AUCTION: 4, TAG_SALE: 3,
              UNCERTAIN: 1}

_ESTATE_SIGNALS = [
    "estate sale", "estate sales", "estate liquidation", "estate of",
    "whole house sale", "house contents", "contents sale", "contents of",
    "downsizing sale", "life long collection", "lifetime collection",
]
_AUCTION_SIGNALS = ["auction"]
_ONLINE_SIGNALS = [
    "online auction", "online only", "online-only", "timed auction",
    "bidding ends", "bidding closes", "hibid", "auctionninja", "maxsold",
    "proxibid", "liveauctioneers", "invaluable.com",
]
_ANTIQUE_EVENT_SIGNALS = [
    "antique show", "antiques show", "antique fair", "antiques fair",
    "antique market", "antiques market", "vintage market", "vintage fair",
    "flea market", "antiques weekend", "antique fest", "vintage pop-up",
    "vintage pop up", "collectibles show", "swap meet",
]
_TAG_SIGNALS = [
    "tag sale", "yard sale", "garage sale", "rummage sale", "barn sale",
    "moving sale", "multi-family sale", "multi family sale", "block sale",
    "stoop sale", "church sale", "attic sale", "porch sale", "shed sale",
    "multifamily sale", "yard/garage sale",
]

_ALL_SALE_SIGNALS = (_ESTATE_SIGNALS + _ANTIQUE_EVENT_SIGNALS + _TAG_SIGNALS
                     + ["estate auction", "antique auction", "auction"])

# Ads to drop: buyers/services fishing for estates, cleanout companies,
# real-estate listings, rentals, job posts.
_REJECT_SIGNALS = [
    "we buy", "i buy", "cash for your", "cash paid for", "looking to buy",
    "wanted:", "wanted -", "we purchase", "buying estates", "buy estates",
    "cleanout service", "clean out service", "cleanouts", "clean-outs",
    "junk removal", "we haul", "hauling service", "estate sale services",
    "we conduct", "hire us", "free appraisal", "appraisal service",
    "for rent", "real estate agent", "realtor", "open house",
    "now hiring", "help wanted", "job opening", "we are hiring",
]

# Item-category tags: (display name, compiled keyword pattern). Word
# boundaries matter ("art" must not fire on "start", "quart", …).
def _kw(*words: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)

_TAGS: list[tuple[str, re.Pattern]] = [
    ("mid-century", _kw("mid[- ]?century", "mcm", "danish modern", "eames",
                        "knoll", "herman miller", "teak", "atomic")),
    ("furniture", _kw("furniture", "dresser", "sideboard", "credenza",
                      "armoire", "hutch", "dining (?:room )?(?:table|set)",
                      "bedroom set", "wardrobe", "vanity", "settee")),
    ("art", _kw("art", "artwork", "paintings?", "prints?", "sculptures?",
                "lithographs?", "etchings?", "watercolors?")),
    ("jewelry & watches", _kw("jewelry", "jewellery", "watches", "costume jewelry",
                              "gold", "rings?", "brooch(?:es)?")),
    ("silver", _kw("sterling", "silverware", "silver", "flatware")),
    ("china & glass", _kw("china", "porcelain", "crystal", "glassware",
                          "stoneware", "pottery", "ceramics?",
                          "depression glass", "milk glass")),
    ("vinyl & audio", _kw("records?", "vinyl", "lps?", "turntables?", "stereo",
                          "hi-?fi", "45s", "78s")),
    ("books & ephemera", _kw("books?", "ephemera", "postcards?", "magazines?",
                             "comics?", "maps?", "documents")),
    ("tools", _kw("tools?", "woodworking", "machinist", "power tools",
                  "hand tools", "workshop")),
    ("vintage clothing", _kw("vintage cloth(?:ing|es)", "furs?", "workwear",
                             "denim", "hats", "handbags?", "purses?")),
    ("toys & games", _kw("toys?", "dolls?", "model trains?", "board games?",
                         "games", "lego")),
    ("rugs & textiles", _kw("rugs?", "quilts?", "textiles?", "linens?",
                            "persian rug", "tapestr(?:y|ies)")),
    ("lighting", _kw("lamps?", "lighting", "chandeliers?", "sconces?")),
    ("primitives & country", _kw("primitives?", "farmhouse", "crocks?",
                                 "country antiques", "folk art", "americana")),
    ("industrial & salvage", _kw("industrial", "salvage", "architectural")),
    ("coins & stamps", _kw("coins?", "numismatic", "stamps?", "currency")),
    ("militaria", _kw("militaria", "military", "wwii", "ww2", "civil war")),
    ("cameras & electronics", _kw("cameras?", "radios?", "vintage electronics",
                                  "typewriters?")),
    ("garden & outdoor", _kw("garden", "patio", "wrought iron", "urns?",
                             "outdoor furniture")),
]

# ---------------------------------------------------------------- regions ---
NYC = "NYC"
HUDSON_VALLEY = "HUDSON_VALLEY"
CATSKILLS = "CATSKILLS"
NEARBY = "NEARBY"
UNKNOWN = "UNKNOWN"

# Distinctive phrases safe to match anywhere in the ad text.
_STRONG = {
    NYC: ["new york city", "nyc", "manhattan", "brooklyn", "the bronx",
          "staten island", "harlem", "astoria", "greenpoint", "bushwick",
          "flatbush", "long island city", "upper east side", "upper west side",
          "queens"],
    HUDSON_VALLEY: ["hudson valley", "westchester", "dutchess county",
                    "ulster county", "putnam county", "rockland county",
                    "poughkeepsie", "new paltz", "rhinebeck", "saugerties",
                    "cold spring", "beacon ny", "sleepy hollow", "nyack",
                    "tarrytown", "peekskill", "newburgh", "yonkers",
                    "white plains", "mount kisco", "katonah", "croton",
                    "wappingers", "hyde park", "kerhonkson", "rosendale",
                    "stone ridge", "high falls", "phoenicia", "woodstock ny",
                    "boiceville", "shandaken", "hurley ny", "port ewen",
                    "gardiner ny", "ellenville", "marlboro ny", "milton ny",
                    "walden ny", "pine bush", "montgomery ny", "goshen ny",
                    "warwick ny", "chester ny", "monroe ny", "middletown ny",
                    "port jervis", "cornwall ny", "new windsor", "fishkill",
                    "pawling", "millbrook", "millerton", "amenia", "red hook ny",
                    "tivoli ny", "germantown ny", "hillsdale ny", "copake",
                    "chatham ny", "kinderhook", "valatie", "ghent ny",
                    "claverack", "hudson ny", "catskill ny", "coxsackie",
                    "athens ny", "cairo ny", "windham ny", "tannersville",
                    "hunter ny", "greene county", "columbia county"],
    CATSKILLS: ["sullivan county", "sullivan catskills", "upper delaware",
                "monticello ny", "liberty ny", "callicoon", "narrowsburg",
                "livingston manor", "roscoe ny", "jeffersonville ny",
                "youngsville ny", "bethel ny", "white lake ny",
                "kauneonga lake", "swan lake ny", "eldred ny", "barryville",
                "glen spey", "pond eddy", "wurtsboro", "rock hill ny",
                "hurleyville", "fallsburg", "south fallsburg", "woodbourne",
                "woodridge ny", "loch sheldrake", "grahamsville", "neversink",
                "claryville", "bloomingburg", "forestburgh", "mountain dale",
                "mountaindale", "smallwood ny", "lake huntington", "cochecton",
                "long eddy", "hankins ny", "north branch ny", "hortonville ny",
                # Catskills-adjacent Delaware County
                "hancock ny", "east branch ny", "fishs eddy", "downsville",
                "walton ny", "delhi ny", "andes ny", "margaretville",
                "arkville", "fleischmanns", "bovina",
                # PA side of the Upper Delaware, across from Sullivan
                "honesdale", "hawley pa", "lackawaxen", "shohola",
                "beach lake", "damascus pa", "milford pa", "matamoras"],
    NEARBY: ["long island", "nassau county", "suffolk county", "new jersey",
             "north jersey", "bergen county", "connecticut", "fairfield county",
             "litchfield county", "albany ny", "capital region", "berkshires",
             "poconos", "oneonta", "cooperstown", "binghamton"],
}

# Bare town names safe to match only in the short location field
# ("Monticello, NY 12701") where there's no prose to collide with.
_LOC_ONLY = {
    HUDSON_VALLEY: ["kingston", "beacon", "woodstock", "hurley", "gardiner",
                    "marlboro", "milton", "walden", "montgomery", "goshen",
                    "warwick", "chester", "monroe", "middletown", "cornwall",
                    "red hook", "tivoli", "germantown", "hillsdale", "chatham",
                    "ghent", "hudson", "catskill", "athens", "cairo", "windham",
                    "hunter", "highland", "accord", "olivebridge", "west shokan",
                    "mount tremper", "bearsville", "clintondale", "modena",
                    "wallkill", "circleville", "otisville", "westtown",
                    "greenwood lake", "highland falls", "garrison", "carmel",
                    "mahopac", "brewster", "patterson", "dover plains",
                    "stanfordville", "pleasant valley", "lagrangeville",
                    "hopewell junction", "stormville", "holmes", "wingdale"],
    CATSKILLS: ["monticello", "liberty", "roscoe", "jeffersonville",
                "youngsville", "bethel", "white lake", "swan lake", "eldred",
                "rock hill", "woodridge", "hankins", "north branch",
                "hortonville", "smallwood", "hancock", "east branch",
                "hawley", "damascus", "milford"],
    NYC: ["new york", "bronx", "ridgewood", "maspeth", "woodside", "sunnyside",
          "jackson heights", "forest hills", "bayside", "whitestone",
          "college point", "far rockaway", "riverdale", "pelham bay"],
}

# Zip-code prefixes (first 3 digits). NYC boroughs; Hudson Valley counties
# (Westchester/Putnam/Rockland/Orange 105-109, Ulster/Greene 124, Dutchess/
# Ulster 125-126); Sullivan 127 plus Wayne/Pike PA 183-184 across the river.
_ZIP_PREFIX = {}
for p in ("100", "101", "102", "103", "104", "111", "112", "113", "114", "116"):
    _ZIP_PREFIX[p] = NYC
for p in ("105", "106", "107", "108", "109", "124", "125", "126"):
    _ZIP_PREFIX[p] = HUDSON_VALLEY
for p in ("127", "183", "184"):
    _ZIP_PREFIX[p] = CATSKILLS
for p in ("110", "115", "117", "118", "119", "120", "121", "122", "123",
          "128", "130", "137", "138", "139"):
    _ZIP_PREFIX[p] = NEARBY

_ZIP_LOC_RE = re.compile(r"\b(\d{5})\b")
# In prose, only trust zips that follow a state abbreviation/name.
_ZIP_TEXT_RE = re.compile(
    r"\b(?:ny|nj|ct|pa|new york|new jersey|connecticut|pennsylvania)\.?,?\s+"
    r"(\d{5})\b", re.I)

# States that mean a sale is out of scope (aggregator hub pages mix in
# featured sales from anywhere). Checked only after in-scope place names, so
# the PA Upper Delaware towns still win. Runs on RAW lowercased text:
# two-letter codes only in the ", ST" address form ("Bryn Mawr, PA") — bare
# "pa"/"ma"/"me" are English words — plus unambiguous full state names.
# "Delaware" is deliberately absent (Upper Delaware / Delaware County NY).
_OUT_OF_SCOPE_RE = re.compile(
    r",\s*(?:pa|vt|ma|nh|ri|me|md|va|dc|oh|fl|nc|sc|ga|tx|ca|wv)\b"
    r"|\b(?:pennsylvania|vermont|massachusetts|new hampshire|rhode island|"
    r"maryland|virginia|west virginia|ohio|florida|california|texas|"
    r"georgia|north carolina|south carolina)\b")


def _norm(text: str) -> str:
    """Lowercase; collapse punctuation/whitespace so 'Monticello, NY' and
    'monticello ny' compare equal."""
    return re.sub(r"[\s,.;:!()\[\]/]+", " ", (text or "").lower()).strip()


def _phrase_in(phrase: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])",
                     text) is not None


def region_of(sale: Sale) -> str:
    loc = _norm(sale.location)
    head = _norm(f"{sale.title} {sale.location}")
    body = _norm(sale.description)
    raw = (sale.text() or "").lower()

    # 1. The location field, most specific region first. A location naming
    # NJ/CT is authoritative — it beats same-named NY towns (Ridgewood NJ vs
    # Ridgewood Queens). Strong phrases are checked alongside bare towns so
    # "Poughkeepsie, New York" hits Hudson Valley before NYC's "new york".
    if loc:
        if re.search(r"\b(nj|new jersey|ct|conn|connecticut)\b", loc):
            return NEARBY
        for region in (CATSKILLS, HUDSON_VALLEY, NYC):
            for town in _STRONG[region] + _LOC_ONLY.get(region, []):
                if _phrase_in(town, loc):
                    return region

    # 2. Distinctive phrases in the title (in-scope regions first), then the
    # out-of-scope state guard — a title/location naming another state must
    # not fall through to a region hint ("Estate sale — Bryn Mawr, PA" found
    # on an NYC hub page is not an NYC sale).
    for region in (CATSKILLS, HUDSON_VALLEY, NYC, NEARBY):
        for phrase in _STRONG[region]:
            if _phrase_in(phrase, head):
                return region
    if _OUT_OF_SCOPE_RE.search((sale.title + " " + sale.location).lower()):
        return NEARBY

    # 3. Distinctive phrases in the description.
    for region in (CATSKILLS, HUDSON_VALLEY, NYC, NEARBY):
        for phrase in _STRONG[region]:
            if _phrase_in(phrase, body):
                return region

    # 4. Zip codes: bare in the location field, state-prefixed in prose.
    zips = _ZIP_LOC_RE.findall(loc) + _ZIP_TEXT_RE.findall(sale.text() or "")
    for z in zips:
        if z[:3] in _ZIP_PREFIX:
            return _ZIP_PREFIX[z[:3]]
        if z[:2] in ("06", "07", "08"):      # CT / NJ
            return NEARBY

    # 5. Out-of-scope state anywhere in the ad beats the region hint.
    if _OUT_OF_SCOPE_RE.search(raw):
        return NEARBY

    # 6. Fall back to where the listing was found.
    if sale.region_hint in (NYC, HUDSON_VALLEY, CATSKILLS, NEARBY):
        return sale.region_hint
    return UNKNOWN


# ------------------------------------------------------------- relevance ----
def is_relevant(sale: Sale) -> bool:
    """Keep only plausible sale events in scope."""
    # "real estate sale" contains "estate sale"; blank it before matching.
    text = sale.text().lower().replace("real estate", " ")
    if not sale.title or not sale.url:
        return False
    if any(r in text for r in _REJECT_SIGNALS):
        return False
    if any(s in text for s in _ALL_SALE_SIGNALS):
        return True
    # "Antiques"/"vintage" plus an event-ish word still counts (show
    # announcements phrase themselves loosely).
    if (("antique" in text or "vintage" in text or "collectibles" in text)
            and any(w in text for w in ("sale", "show", "market", "fair",
                                        "event", "pop-up", "pop up"))):
        return True
    return False


def classify(sale: Sale) -> Sale:
    text = sale.text().lower().replace("real estate", " ")

    estate = any(s in text for s in _ESTATE_SIGNALS)
    auction = any(s in text for s in _AUCTION_SIGNALS)
    antique_event = any(s in text for s in _ANTIQUE_EVENT_SIGNALS)
    tag = any(s in text for s in _TAG_SIGNALS)
    sale.is_online = any(s in text for s in _ONLINE_SIGNALS)

    if auction:
        sale.sale_type = AUCTION
        sale.type_note = ("Estate auction" if estate else "Auction") + (
            " — online bidding only" if sale.is_online else "")
    elif estate:
        sale.sale_type = ESTATE_SALE
        sale.type_note = "In-person estate sale — whole-house contents"
    elif antique_event:
        sale.sale_type = ANTIQUE_EVENT
        sale.type_note = "Antique/vintage show, fair, or flea market"
    elif tag:
        sale.sale_type = TAG_SALE
        sale.type_note = "Tag / yard / garage / barn sale"
    else:
        sale.sale_type = UNCERTAIN
        sale.type_note = "Sale-ish listing — check the ad for details"

    sale.tags = [name for name, pat in _TAGS if pat.search(sale.text())]
    sale.region = region_of(sale)

    sale.score = _TYPE_RANK[sale.sale_type] * 10 + min(len(sale.tags), 8)
    if "antique" in text or "antiques" in text:
        sale.score += 5
    return sale
