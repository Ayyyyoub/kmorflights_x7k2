"""Entry point: for every (Moroccan origin) x (allowed destination) pair,
fetch the cheapest current fares, and push an ntfy alert for any new
all-time-low or any fare under the configured absolute threshold.

Run once per invocation - scheduling is handled by the Docker loop
(scheduler.py) or the GitHub Actions cron, not by this script.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage import connect, get_best, upsert_best  # noqa: E402
from notifier import send_deal_alert  # noqa: E402
from travelpayouts_client import TravelpayoutsClient, TravelpayoutsError  # noqa: E402
from currency import usd_to_mad  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "state.sqlite3")
DESTINATIONS_PATH = ROOT / "data" / "visa_free_destinations.json"
SAFE_TRANSIT_AIRLINES_PATH = ROOT / "data" / "safe_transit_airlines.json"


def load_safe_transit_airlines() -> set[str]:
    with open(SAFE_TRANSIT_AIRLINES_PATH, encoding="utf-8") as f:
        return set(json.load(f)["safe_hub_airlines"].keys())


def env(key: str, default: str) -> str:
    """os.environ.get() but treats an empty string the same as unset - CI
    systems (e.g. GitHub Actions) set env vars to "" for undefined config
    variables rather than omitting them, which silently broke defaulting.
    """
    value = os.environ.get(key)
    return value if value else default


def load_config() -> dict:
    origins_env = env("ORIGIN_AIRPORTS", "CMN,RBA,RAK,TNG")
    origins = [o.strip().upper() for o in origins_env.split(",") if o.strip()]
    return {
        "origins": origins,
        "currency": env("CURRENCY", "USD"),
        "max_price": float(env("MAX_PRICE_USD", "250")),
        "max_stops": int(env("MAX_STOPS", "1")),
        "improvement_threshold_pct": float(env("IMPROVEMENT_THRESHOLD_PCT", "5")),
        "token": os.environ["TRAVELPAYOUTS_TOKEN"],
        "ntfy_topic": os.environ["NTFY_TOPIC"],
    }


def load_destinations() -> list[dict]:
    with open(DESTINATIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def should_alert(existing: tuple[float, float | None] | None, price: float, improvement_pct: float) -> bool:
    if existing is None:
        return True
    best_price, last_alerted_price = existing
    if price < best_price:
        return True
    reference = last_alerted_price if last_alerted_price is not None else best_price
    return price <= reference * (1 - improvement_pct / 100)


def main() -> None:
    cfg = load_config()
    destinations = load_destinations()
    safe_transit_airlines = load_safe_transit_airlines()
    client = TravelpayoutsClient(cfg["token"])
    now_iso = datetime.now(timezone.utc).isoformat()

    alerts_sent = 0
    checked = 0

    with connect(DB_PATH) as conn:
        for origin in cfg["origins"]:
            for dest in destinations:
                for airport in dest["airports"]:
                    checked += 1
                    try:
                        fares = client.cheapest_fares(origin, airport, currency=cfg["currency"], one_way=False)
                    except TravelpayoutsError as exc:
                        print(f"[warn] {origin}->{airport}: {exc}", file=sys.stderr)
                        time.sleep(1)
                        continue

                    candidates = [
                        f
                        for f in fares
                        if f.stops <= cfg["max_stops"] and (f.stops == 0 or f.airline in safe_transit_airlines)
                    ]
                    if not candidates:
                        time.sleep(0.3)
                        continue
                    cheapest = min(candidates, key=lambda f: f.price)

                    if cheapest.price > cfg["max_price"]:
                        time.sleep(0.3)
                        continue

                    existing = get_best(conn, origin, airport)
                    alert = should_alert(existing, cheapest.price, cfg["improvement_threshold_pct"])

                    if alert:
                        stop_desc = "direct" if cheapest.stops == 0 else f"{cheapest.stops} stop(s)"
                        mad_price = usd_to_mad(cheapest.price) if cfg["currency"] == "USD" else None
                        price_str = f"{cheapest.price:.0f} {cfg['currency']}"
                        if mad_price is not None:
                            price_str += f" (~{mad_price:.0f} MAD)"
                        trip_desc = "round-trip" if cheapest.return_date else "one-way"
                        title = f"{origin} -> {dest['country']} ({airport}): {price_str} {trip_desc}"
                        message = (
                            f"{stop_desc} ({cheapest.airline or '?'}), depart {cheapest.departure_date}"
                            + (f", return {cheapest.return_date}" if cheapest.return_date else "")
                            + f"\nVisa: {dest['visa_category']} (max {dest.get('max_stay_days', '?')} days)"
                        )
                        if cheapest.stops > 0:
                            message += (
                                "\n⚠️ Connecting flight: layover airport isn't confirmed by this API. "
                                "Airline's hub is outside Schengen/UK, but double-check the actual routing on "
                                "the booking page before paying - you don't hold a Schengen visa."
                            )
                        send_deal_alert(cfg["ntfy_topic"], title, message, url=cheapest.link)
                        alerts_sent += 1

                    upsert_best(conn, origin, airport, cheapest.price, cfg["currency"], alert, now_iso)
                    time.sleep(0.3)

    print(f"Checked {checked} origin/destination pairs, sent {alerts_sent} alerts.")


if __name__ == "__main__":
    main()
