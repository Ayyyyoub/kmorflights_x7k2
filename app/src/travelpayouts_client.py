"""Thin wrapper around the Travelpayouts (Aviasales) Data API - free, no
credit card, no request cap for the "prices_for_dates" cheapest-fare
endpoint. Sign up at https://www.travelpayouts.com to get a token.
Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

PRICES_FOR_DATES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


class TravelpayoutsError(RuntimeError):
    pass


@dataclass
class FareResult:
    origin: str
    destination: str
    price: float
    currency: str
    departure_date: str
    return_date: str | None
    stops: int
    return_stops: int
    airline: str | None
    link: str | None
    raw: dict[str, Any]


class TravelpayoutsClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def cheapest_fares(
        self,
        origin: str,
        destination: str,
        currency: str = "EUR",
        one_way: bool = True,
        direct_only: bool = False,
    ) -> list[FareResult]:
        """Cheapest actual fares found recently for this route (direct and
        connecting), one entry per departure date found.
        """
        resp = requests.get(
            PRICES_FOR_DATES_URL,
            headers={"X-Access-Token": self._token},
            params={
                "origin": origin,
                "destination": destination,
                "currency": currency,
                "one_way": str(one_way).lower(),
                "direct": str(direct_only).lower(),
                "sorting": "price",
                "limit": 30,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise TravelpayoutsError(f"prices_for_dates failed {origin}->{destination}: {resp.status_code} {resp.text}")
        body = resp.json()
        if not body.get("success", True):
            return []
        out: list[FareResult] = []
        for item in body.get("data", []):
            out.append(
                FareResult(
                    origin=item.get("origin", origin),
                    destination=item.get("destination", destination),
                    price=float(item.get("price", "nan")),
                    currency=currency,
                    departure_date=item.get("departure_at", "")[:10],
                    return_date=(item.get("return_at") or "")[:10] or None,
                    stops=int(item.get("transfers", 0)),
                    return_stops=int(item.get("return_transfers", 0)),
                    airline=item.get("airline"),
                    link=("https://www.aviasales.com" + item["link"]) if item.get("link") else None,
                    raw=item,
                )
            )
        return out
