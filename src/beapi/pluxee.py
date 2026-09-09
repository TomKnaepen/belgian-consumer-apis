"""Pluxee EVA meal, eco, gift and sport voucher balances.

Pluxee has no consumer API and nothing scrapable: the portal is a single-page
app. The mobile app authenticates against connect.pluxee.app with a native OIDC
client that is granted a refresh token, and this client reuses that mechanism
headlessly:

    refresh_token --(token endpoint)--> short-lived access_token
    access_token  --(EVA consumer BFF)--> card balances

The refresh token is obtained once through the app's authorization-code + PKCE
flow, with a human solving the login. It ROTATES on every use: the replacement
is handed to `on_rotate` before the balance call, and losing it means redoing
the browser login. The issuer renews a roughly 14-day TTL on each use, so any
polling interval under that keeps it alive indefinitely.

Only one process may ever hold a given refresh token. Two pollers sharing one
seed will invalidate each other.

See docs/reverse-engineering/pluxee.md for the full derivation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from ._http import client as _make_client
from ._http import request as _request
from .credentials import Credential, TokenStore, resolve
from .errors import AuthExpired, ContractError, UpstreamError

TOKEN_URL = "https://connect.pluxee.app/op/oidc/token"
CARDS_URL = "https://api.pluxee.app/gl/eva/bff/v2/be/cards"
PORTAL_ORIGIN = "https://consumers.pluxee.be"

PASS_TYPES = {
    "lunch": "W1",
    "gift": "W2",
    "eco": "W4",
    "sport": "W5",
}

_EXPIRED = (
    "The Pluxee refresh token was rejected. It has expired or been revoked — "
    "redo the one-time mobile-app login to obtain a new one."
)


class Pluxee:
    def __init__(
        self,
        *,
        refresh_token: Credential,
        client_id: Credential,
        subscription_key: Credential,
        on_rotate: Callable[[str], None] | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> None:
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._subscription_key = subscription_key
        self._on_rotate = on_rotate
        self._session = session
        self._owns_session = session is None

    @classmethod
    def from_store(
        cls,
        store: TokenStore,
        user: str,
        *,
        client_id: Credential,
        subscription_key: Credential,
        session: httpx.AsyncClient | None = None,
    ) -> Pluxee:
        return cls(
            refresh_token=store.reader(user),
            client_id=client_id,
            subscription_key=subscription_key,
            on_rotate=lambda token: store.set(user, token),
            session=session,
        )

    async def __aenter__(self) -> Pluxee:
        if self._session is None:
            self._session = _make_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.aclose()
            self._session = None

    async def access_token(self) -> str:
        """Exchange the refresh token, persisting the rotated one before returning.

        The rotation is persisted first and the caller's balance request only
        happens after: an exchange whose replacement was never stored has burned
        the stored token, and the next run would authenticate with a dead value.
        """
        if self._session is None:
            raise RuntimeError("Use Pluxee as an async context manager, or pass a session.")
        current = resolve(self._refresh_token, "PLUXEE_REFRESH_TOKEN")
        try:
            payload = await _request(
                self._session,
                "POST",
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": resolve(self._client_id, "PLUXEE_CLIENT_ID"),
                    "refresh_token": current,
                },
                headers={"Accept": "application/json"},
                auth_expired_message=_EXPIRED,
            ) or {}
        except UpstreamError as exc:
            # A spent or revoked refresh token comes back as OAuth's
            # invalid_grant, which RFC 6749 carries on a 400 — not the 401 the
            # generic mapping treats as an expiry.
            if exc.status == 400 and "invalid_grant" in exc.body:
                raise AuthExpired(_EXPIRED) from exc
            raise

        rotated = payload.get("refresh_token")
        if rotated and rotated != current and self._on_rotate is not None:
            self._on_rotate(rotated)

        access = payload.get("access_token")
        if not access:
            raise ContractError("Pluxee token response carried no access_token")
        return access

    async def cards(self) -> dict[str, Any]:
        access = await self.access_token()
        return await _request(
            self._session,
            "GET",
            CARDS_URL,
            headers={
                "Authorization": f"Bearer {access}",
                "authorization-version": "2",
                "ocp-apim-subscription-key": resolve(
                    self._subscription_key, "PLUXEE_SUBSCRIPTION_KEY"
                ),
                "Accept": "*/*",
                "Origin": PORTAL_ORIGIN,
                "Referer": f"{PORTAL_ORIGIN}/",
            },
            auth_expired_message=_EXPIRED,
        ) or {}

    async def balance(self, voucher: str = "lunch") -> dict[str, Any]:
        """Return ``{"balance": float, "expiry": "YYYY-MM-DD" | ""}`` for one pass type.

        `expiry` is the money's own expiry date, not a credential's — this
        client's credential renews itself.
        """
        return extract_balance(await self.cards(), PASS_TYPES.get(voucher, voucher))


def extract_balance(cards: dict, pass_type: str) -> dict[str, Any]:
    for card in cards.get("cards", []):
        for benefit in card.get("benefits", []):
            if benefit.get("externalProductType") != pass_type:
                continue
            amount = benefit["amount"]
            expiring = benefit.get("expiringBalances") or []
            return {
                "balance": amount["value"] / (10 ** amount["exponent"]),
                "expiry": (expiring[0].get("expiryDate") or "")[:10] if expiring else "",
            }
    raise ContractError(f"pass type {pass_type} not present in the cards response")
