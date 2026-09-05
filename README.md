# Antiques & Estate Sale Hunter 🏺

Daily automated scan for **antique sales, estate sales, auctions, antique
shows/flea markets, and tag/yard/barn sales** in and around **New York
City**, the **Hudson Valley**, and the **Sullivan County Catskills** (plus
the PA side of the Upper Delaware). Results arrive two ways:

- **A daily HTML email digest** — grouped by region, ordered by sale date,
  with what-they-have tags, TODAY / THIS WEEKEND flags, and direct links.
- **A full web board** (`docs/index.html`, served by GitHub Pages) — every
  tracked sale, uncapped, where **each sale card has a stable anchor id** so
  you can link a friend straight to one sale: click the `🔗 anchor` link on
  any card (or `🔗 share` in the email) and send the URL, e.g.
  `https://meandavejustice.github.io/antiques/#sale-craigslist-7712345678`.

## What it scans

| Source | How | Notes |
|---|---|---|
| **Craigslist** | Static SEO search results + one ad-page fetch per new listing | NY-area subdomains (newyork, hudsonvalley, catskills, albany, longisland, newjersey, poconos) × garage-sale + antiques categories + free-text queries. Search results carry no dates, so each new ad's page is fetched once (capped at 150/run) for its sale dates, address, and body text; results are cached in the seen-state |
| **EstateSales.NET** | JSON-LD events + link harvest on city hub pages | NYC / Poughkeepsie–Kingston / Monticello–Liberty hubs |
| **estatesales.org** | Same generic parser | NY state page |
| **AuctionZip** | Same | Zip-radius searches on 10001 / 12401 / 12701 |
| **AuctionNinja** | Same | Big in the NY-metro/Hudson Valley estate-auction scene |
| **HiBid** | Same | Online estate auctions; flagged "ONLINE BIDDING" |
| **Antiques & The Arts Weekly** | Same | Show/fair calendar |
| **Web discovery** | DuckDuckGo (keyless) or Brave Search API | Catches sale companies' own sites, promoters, local-paper calendars |

Every digest ends with a **source health table**, so a blocked or redesigned
site is visible immediately instead of silently disappearing. Sites that turn
out to be JS-only render as "no sale links found" — swap in better URLs in
`config.yaml` or drop them.

### Not scannable (check manually)
- **Facebook Marketplace / local Facebook groups** — aggressively blocks
  automation; a lot of yard-sale traffic lives there.
- **Instagram-only sale companies** — login-walled; web discovery sometimes
  surfaces their websites.
- **gsalr.com / MaxSold** — hard-block CI requests with 403s. Craigslist
  covers the garage-sale beat; MaxSold auctions surface via web discovery.

## How listings are organized

**Regions** (each digest section, ordered by sale date within):

1. 🗽 **New York City** — the five boroughs.
2. 🏞️ **Hudson Valley** — Westchester, Putnam, Rockland, Orange, Dutchess,
   Ulster, Columbia, Greene.
3. 🎣 **Sullivan County Catskills & Upper Delaware** — Sullivan plus the
   Catskills side of Delaware County and the PA river towns (Honesdale,
   Lackawaxen, Milford…).
4. 📍 **Nearby & unplaced** — Long Island, North Jersey, Connecticut, the
   Capital Region, plus anything whose location couldn't be pinned down.

Region assignment reads place names and zip codes out of each ad
(`scanner/classify.py` holds the town/zip tables — tune freely), falling
back to which regional page/subdomain the listing was found on.

**Sale types**: `ESTATE SALE` · `AUCTION` (online-only auctions get an extra
flag) · `ANTIQUE SHOW / MARKET` · `TAG / YARD SALE` — plus **item tags**
extracted from the ad text (mid-century, art, silver, china & glass, vinyl &
audio, tools, primitives & country, militaria, …) so you can see at a glance
what a sale has.

**Dates**: parsed from every format sellers use ("Aug 15-17", "Fri 8/15 to
Sun 8/17", "starts Sept. 5th"…), and cached in the seen-state so an ad's
page is never fetched twice. Sales that already ended are hidden; sales
happening now get **TODAY / ON NOW**, and weekend ones **THIS WEEKEND**.
Undated sales sort last in each region with a "check the listing" note —
and are dropped 10 days after first sighting, since a sale whose ad has
lingered that long with no parseable date is over even if the ad is still
up.

The filter also drops the classic junk: "we buy estates" ads, cleanout
services, real-estate listings ("real estate sale…"), job posts, and
single-item ads.

## Setup (one-time, ~10 minutes)

The scan runs via GitHub Actions on a daily cron — **schedules only fire on
the default branch**, so merge this branch to `main` to activate it.

### 1. Required: SMTP secrets (for the email)

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` (or `465` for implicit TLS) |
| `SMTP_USERNAME` | the sending account, e.g. `you@gmail.com` |
| `SMTP_PASSWORD` | for Gmail: an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA), **not** your normal password |
| `DIGEST_TO` | optional — defaults to `work@justice.engineering` (set in `config.yaml`) |
| `DIGEST_FROM` | optional — defaults to `SMTP_USERNAME` |

Any SMTP provider works (Gmail, Fastmail, Resend `smtp.resend.com`,
SendGrid `smtp.sendgrid.net`, …).

### 2. Required for the shareable board: GitHub Pages

**Settings → Pages → Deploy from a branch** → pick the default branch and
`/docs`. The board then lives at
`https://meandavejustice.github.io/antiques/` (update `board_url` in
`config.yaml` if you use a custom domain — the email's share links point
there).

### 3. Optional: Brave key for web discovery

Web discovery works out of the box via DuckDuckGo's keyless HTML endpoint.
For a more robust API-backed version, get a free key at
[brave.com/search/api](https://brave.com/search/api) (free tier: 2,000
queries/month; the daily run uses ~8) and add it as a `BRAVE_API_KEY`
secret.

### 4. Test it

Actions tab → **Daily Sale Scan** → **Run workflow**. Check your inbox and
the run log's source-health output; the digest is also attached to the run
as an artifact, and `docs/index.html` gets committed so the Pages board
updates.

## Running locally

```bash
pip install -r requirements.txt
export SMTP_HOST=... SMTP_USERNAME=... SMTP_PASSWORD=...   # optional
python -m scanner.main        # writes digest.html + docs/index.html; emails if SMTP is set
```

## Tuning

- **`config.yaml`** — Craigslist subdomains/categories/queries, the
  sale-site URL list (each site is just a name + candidate URLs for the
  generic parser), discovery queries, recipient, board URL.
- **`scanner/classify.py`** — region town/zip tables, sale-type keywords,
  item-tag vocabularies, junk filters.
- **`scanner/dates.py`** — date formats.

State (already-seen sales, for the NEW badges) is committed to
`data/seen_sales.json` by the workflow after each run; sales unseen for 60
days expire from it automatically.
