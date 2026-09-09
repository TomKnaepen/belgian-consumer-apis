"""Monizze meal, eco and gift voucher balances.

One authenticated GET against the happy.monizze.be API. The credential is the
bearer JWT the my.monizze.be single-page app holds; there is no refresh flow
reachable from outside the app, so the token is captured from a logged-in
browser and lasts around two months. Its `exp` claim is decoded locally so a
caller can warn before it lapses instead of discovering it at the till.

See docs/reverse-engineering/monizze.md for how to capture the token.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from ._http import client as _make_client
from ._http import request as _request
from .credentials import Credential, resolve

BALANCES_URL = "https://happy.monizze.be/api/services/my-monizze/voucher/balances"

VOUCHER_TYPES = {
    "meal": "emv",
    "eco": "eco",
    "gift": "gift",
    "consumption": "cons",
}

_EXPIRED = (
    "The Monizze token was rejected. Capture a fresh bearer token from a "
    "logged-in my.monizze.be session."
)


def token_expiry(token: str) -> tuple[str, int]:
    """Decode the JWT `exp` claim into (iso_date, days_left).

    Returns ("unknown", -1) for anything that does not decode: the token is
    opaque to us beyond this claim, and a caller must not treat a parse failure
    as an expiry.
    """
    try:
        payload = token.split(" ")[-1].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        expires = datetime.fromtimestamp(claims["exp"], tz=UTC)
    except Exception:
        return "unknown", -1
    return expires.strftime("%Y-%m-%d"), (expires - datetime.now(tz=UTC)).days


class Monizze:
    def __init__(
        self,
        *,
        token: Credential,
        session: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Monizze:
        if self._session is None:
            self._session = _make_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.aclose()
            self._session = None

    def _resolved_token(self) -> str:
        token = resolve(self._token, "MONIZZE_TOKEN")
        return token if token.lower().startswith("bearer ") else f"Bearer {token}"

    async def balances(self) -> dict[str, Any]:
        """Raw per-voucher-type balances, keyed by Monizze's own short codes."""
        if self._session is None:
            raise RuntimeError("Use Monizze as an async context manager, or pass a session.")
        payload = await _request(
            self._session,
            "GET",
            BALANCES_URL,
            headers={
                "Authorization": self._resolved_token(),
                "Accept": "application/json",
                "Origin": "https://my.monizze.be",
                "Referer": "https://my.monizze.be/",
            },
            auth_expired_message=_EXPIRED,
        )
        return (payload or {}).get("data") or {}

    async def balance(self, voucher: str = "meal") -> float:
        key = VOUCHER_TYPES.get(voucher, voucher)
        return float(((await self.balances()).get(key) or {}).get("total") or 0.0)

    def expiry(self) -> tuple[str, int]:
        return token_expiry(resolve(self._token, "MONIZZE_TOKEN"))
