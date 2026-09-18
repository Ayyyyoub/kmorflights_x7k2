"""Live USD -> MAD conversion, for display only (fares are fetched/compared
in USD). Uses open.er-api.com - free, no API key, no signup.
"""
from __future__ import annotations

import time

import requests

RATE_URL = "https://open.er-api.com/v6/latest/USD"
_CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, float]] = {}


def usd_to_mad(amount_usd: float) -> float | None:
    cached = _cache.get("USD_MAD")
    if cached and time.time() - cached[1] < _CACHE_TTL_SECONDS:
        rate = cached[0]
    else:
        try:
            resp = requests.get(RATE_URL, timeout=10)
            resp.raise_for_status()
            rate = float(resp.json()["rates"]["MAD"])
        except Exception:
            return None
        _cache["USD_MAD"] = (rate, time.time())
    return amount_usd * rate
