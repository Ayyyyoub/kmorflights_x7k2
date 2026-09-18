# Project recap — morflights

Read this first if picking the project back up later. Context for the "why"
behind decisions that aren't obvious from the code alone.

## What this is

A free flight-deal tracker for a Moroccan traveler (no Schengen visa).
Watches routes from Morocco to destinations that are visa-free/on-arrival/
easy-e-visa for Moroccan passport holders, plus Turkey and Saudi Arabia
unconditionally (explicitly requested regardless of visa list). Pushes
iPhone notifications via ntfy.sh when a route hits a new low round-trip
price.

- Repo: https://github.com/Ayyyyoub/kmorflights_x7k2
- Local path: `D:\Master IT\claude-test`
- Runs in two places simultaneously (redundancy): local Docker (always-on
  home machine) and GitHub Actions cron (every 6h), **on purpose** — see
  "Known quirks" below for what that trade-off costs.

## Key decisions and why

- **Language/stack:** Python, SQLite for price history, Docker for local
  hosting, GitHub Actions for free cloud hosting. Chosen for zero cost and
  minimal moving parts.
- **Flight data source:** Amadeus for Developers self-service was the
  original plan but **was decommissioned** (discovered mid-build, July
  2025). Switched to **Travelpayouts** (Aviasales affiliate Data API) —
  free forever, no card, `prices_for_dates` endpoint gives real cheapest
  fares including connections. Requires a free account + token from
  travelpayouts.com (Profile -> API token tab).
- **Currency:** Fares are priced in **USD** (MAD isn't supported by the
  price API). Each alert also shows a live USD->MAD conversion via
  open.er-api.com (free, no key). `MAX_PRICE_USD` is compared against
  **round-trip** fares, not one-way — this was a real bug early on (see
  Known quirks).
- **Schengen/UK transit-visa safety filter:** the user holds no Schengen
  visa, so any connecting flight through a Schengen/UK airport would need
  an Airport Transit Visa. The free API **does not expose the actual
  layover airport** — only airline code and stop count. Fix:
  `app/data/safe_transit_airlines.json` allowlists airlines with a
  confirmed non-Schengen/UK hub (Turkish Airlines, Gulf carriers, EgyptAir,
  Royal Air Maroc, etc.); connecting itineraries on any other airline are
  dropped. This is a heuristic, not a guarantee — alerts on connecting
  flights include a manual-check reminder.
- **Destination list** (`app/data/visa_free_destinations.json`, 35
  entries): AI-researched starter list (via Antigravity CLI), not
  authoritative — visa rules change, verify before booking.
- **Notifications:** ntfy.sh, chosen over Telegram/Pushover for zero setup
  (just install the iOS app and subscribe to a topic name, no account).
  Two separate topics are used on purpose so the user can tell which
  runner fired an alert:
  - Local Docker -> `flights_notify_x7k2`
  - GitHub Actions -> `flights_notify_x7k2_github`

## Current config (as of last session)

- Origins: `CMN,RBA,RAK,TNG` (Casablanca, Rabat, Marrakesh, Tangier)
- `MAX_PRICE_USD=250` (round-trip), `MAX_STOPS=1`,
  `IMPROVEMENT_THRESHOLD_PCT=5`, `CHECK_INTERVAL_SECONDS=21600` (6h)
- Local secrets live in `.env` (gitignored, never committed)
- Cloud secrets/variables live in GitHub repo Settings -> Secrets and
  variables -> Actions (`TRAVELPAYOUTS_TOKEN`, `NTFY_TOPIC` as secrets;
  `ORIGIN_AIRPORTS`, `CURRENCY`, `MAX_PRICE_USD`, `MAX_STOPS`,
  `IMPROVEMENT_THRESHOLD_PCT` as variables)

## Known quirks / things that bit us once

- **GitHub Actions unset variable != unset env var.** `${{ vars.FOO }}`
  for an undefined repo variable renders as an empty string, which is set
  as the env var — this silently broke Python's `os.environ.get(key,
  default)` fallback (empty string is "present", so the default never
  kicks in). `ORIGIN_AIRPORTS` was missing for the first 3 cloud runs,
  which "succeeded" while silently checking **0 routes**. Fixed by a
  custom `env()` helper in `app/src/main.py` that treats `""` as unset
  everywhere. Worth remembering if adding new config vars later — use
  `env()`, not `os.environ.get()`, for anything sourced from GH Actions.
- **Local Docker and GitHub Actions keep separate SQLite price histories**
  — they don't share state. If the same deal appears in both, you'll get
  two notifications (one per topic). This is accepted as the cost of
  redundancy; not deduplicated on purpose.
- **First run (or any run after clearing/resetting the price-history DB)
  will alert on every qualifying route at once** — expected, not a bug.
  Subsequent runs only alert on genuine new lows or drops of at least
  `IMPROVEMENT_THRESHOLD_PCT`.
- If you change filtering logic (e.g. edit `safe_transit_airlines.json` or
  the price/stop thresholds), the old SQLite/GitHub Actions cache baseline
  can be stale relative to the new logic — either accept a one-time
  self-correcting quiet run, or wipe `app/data/state.sqlite3` locally /
  delete the `morflights-state-*` caches under repo Actions -> Caches to
  force a clean reseed.

## Where to look for what

- Core logic: `app/src/main.py`
- Fare fetching: `app/src/travelpayouts_client.py`
- Visa-safe destination list: `app/data/visa_free_destinations.json`
- Schengen-transit airline allowlist: `app/data/safe_transit_airlines.json`
- Local scheduling loop: `app/src/scheduler.py`
- Cloud scheduling: `.github/workflows/check-flights.yml`
- Setup instructions: `README.md`
