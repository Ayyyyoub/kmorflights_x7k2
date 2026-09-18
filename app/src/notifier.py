"""Push notifications via ntfy.sh (free, no account needed).

Install the ntfy app on your iPhone, subscribe to your topic (set via the
NTFY_TOPIC env var - pick something private/random, e.g. "morflights-8f2a"),
and you'll get a real push notification whenever this fires.
"""
from __future__ import annotations

import requests

NTFY_BASE = "https://ntfy.sh"


def send_deal_alert(topic: str, title: str, message: str, url: str | None = None, priority: int = 4) -> None:
    headers = {
        "Title": title,
        "Priority": str(priority),
        "Tags": "airplane,moneybag",
    }
    if url:
        headers["Click"] = url
    resp = requests.post(f"{NTFY_BASE}/{topic}", data=message.encode("utf-8"), headers=headers, timeout=15)
    resp.raise_for_status()
