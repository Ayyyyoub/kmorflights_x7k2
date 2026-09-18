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

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "state.sqlite3")
DESTINATIONS_PATH = ROOT / "data" / "visa_free_destinations.json"


def load_config() -> dict:
    origins_env = os.environ.get("ORIGIN_AIRPORTS", "CMN,RBA,RAK,TNG")
    origins = [o.strip().upper() for o in origins_env.split(",") if o.strip()]
    return {
        "origins": origins,
        "currency": os.environ.get("CURRENCY", "EUR"),
        "max_price_eur": float(os.environ.get("MAX_PRICE_EUR", "250")),
        "max_stops": int(os.environ.get("MAX_STOPS", "1")),
        "improvement_threshold_pct": float(os.environ.get("IMPROVEMENT_THRESHOLD_PCT", "5")),
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
                        fares = client.cheapest_fares(origin, airport, currency=cfg["currency"])
                    except TravelpayoutsError as exc:
                        print(f"[warn] {origin}->{airport}: {exc}", file=sys.stderr)
                        time.sleep(1)
                        continue

                    candidates = [f for f in fares if f.stops <= cfg["max_stops"]]
                    if not candidates:
                        time.sleep(0.3)
                        continue
                    cheapest = min(candidates, key=lambda f: f.price)

                    if cheapest.price > cfg["max_price_eur"]:
                        time.sleep(0.3)
                        continue

                    existing = get_best(conn, origin, airport)
                    alert = should_alert(existing, cheapest.price, cfg["improvement_threshold_pct"])

                    if alert:
                        stop_desc = "direct" if cheapest.stops == 0 else f"{cheapest.stops} stop(s)"
                        title = f"{origin} -> {dest['country']} ({airport}): {cheapest.price:.0f} {cfg['currency']}"
                        message = (
                            f"{stop_desc}, depart {cheapest.departure_date}"
                            + (f", return {cheapest.return_date}" if cheapest.return_date else "")
                            + f"\nVisa: {dest['visa_category']} (max {dest.get('max_stay_days', '?')} days)"
                        )
                        send_deal_alert(cfg["ntfy_topic"], title, message, url=cheapest.link)
                        alerts_sent += 1

                    upsert_best(conn, origin, airport, cheapest.price, cfg["currency"], alert, now_iso)
                    time.sleep(0.3)

    print(f"Checked {checked} origin/destination pairs, sent {alerts_sent} alerts.")


if __name__ == "__main__":
    main()
