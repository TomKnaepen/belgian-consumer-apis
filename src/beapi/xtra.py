"""Colruyt Xtra shopping list and product catalogue.

Undocumented BFF endpoints behind www.colruyt.be. Authentication is one opaque
session cookie plus the site-wide static API key — the OAuth tokens live
server-side in the backend-for-frontend, so there is nothing to refresh here.
The session cookie expires roughly every two months and must be re-copied from
a logged-in browser.

Product search needs only the API key, so it keeps working after the cookie
lapses.

See docs/reverse-engineering/xtra.md for how to obtain both credentials.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from ._http import client as _make_client
from ._http import request as _request
from .credentials import Credential, resolve
from .errors import ContractError

BFF = "https://apix.colruyt.be/gateway/emec.colruyt.bffsvc/cg"
SEARCH = (
    "https://apip.colruyt.be/gateway/emec.colruyt.protected.bffsvc"
    "/cg/nl/api/product-search-prs"
)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

_EXPIRED = (
    "The clpbff_session cookie was rejected. Copy a fresh one from a logged-in "
    "browser (DevTools → Application → Cookies → www.colruyt.be)."
)


def _find_items(payload: Any) -> list | None:
    """Locate the item array, whose wrapper differs per endpoint.

    `add-items-to-list` answers `{"items": [...]}`, while `latest-shopping-list`
    answers `{"getListItems": {"data": [...], ...}, "getListModel": {...}}` —
    no `items` key at all. The recursive fallback keeps a further rename from
    reading as an empty list.

    Returns None rather than [] when nothing is found, so a changed response
    shape is reported instead of being mistaken for an empty shopping list.
    """
    if isinstance(payload, dict):
        listing = payload.get("getListItems")
        if isinstance(listing, dict) and isinstance(listing.get("data"), list):
            return listing["data"]
        if isinstance(payload.get("items"), list):
            return payload["items"]
        candidates = payload.values()
    elif isinstance(payload, list):
        candidates = payload
    else:
        return None
    for value in candidates:
        found = _find_items(value)
        if found is not None:
            return found
    return None


def _unwrap(payload: Any) -> list[dict]:
    items = _find_items(payload)
    if items is None:
        shape = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise ContractError(f"Xtra response carried no items array (payload shape: {shape})")
    return items


def _as_iso(value: Any) -> Any:
    """`latest-shopping-list` returns epoch seconds where other endpoints send ISO."""
    if isinstance(value, (int, float)):
        return (
            datetime.fromtimestamp(value, UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    return value


def _normalise(item: dict) -> dict:
    product = item.get("productData") or {}
    return {
        "id": item.get("id"),
        "description": item.get("description"),
        "completed": item.get("completedAt") is not None,
        "product_id": product.get("productId"),
        "quantity": product.get("quantity"),
        "category": item.get("category"),
        "created_at": _as_iso(item.get("createdAt")),
    }


def _normalise_product(product: dict) -> dict:
    price = product.get("price") or {}
    return {
        # `name` is the bare product ("bananen"); `long_name` already includes
        # brand and content ("BONI bananen ±1kg"). Keeping them separate stops
        # callers composing "BONI BONI bananen ±1kg (±1kg)".
        "product_id": product.get("technicalArticleNumber"),
        "name": product.get("name"),
        "long_name": product.get("LongName"),
        "brand": product.get("brand"),
        "content": product.get("content"),
        "price": price.get("basicPrice"),
        "in_promo": bool(product.get("inPromo")),
        "image": product.get("fullImage"),
        "thumbnail": product.get("thumbNail"),
        "available": bool(product.get("isAvailable")),
    }


def _now_iso() -> str:
    """Millisecond-precision UTC, matching the format the web client sends."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_entry(entry: dict) -> dict:
    """Build one add-items payload entry.

    The id and timestamps are generated client-side — the web client mints a
    uuid4 and the server stores and echoes it rather than assigning its own.
    """
    now = _now_iso()
    return {
        "id": str(uuid.uuid4()),
        "createdAt": now,
        "updatedAt": now,
        "completedAt": None,
        "description": entry["description"],
        "productData": {
            "productId": str(entry["product_id"]),
            "quantity": entry.get("quantity") or 1,
            "unitCode": "P",
        },
    }


def _match_entry(items: list[dict], entry: dict) -> dict | None:
    """Find the list item corresponding to a requested add entry.

    `add-items-to-list` answers with the whole list, not just what changed, so
    the requested entry has to be picked back out of it.
    """
    for item in items:
        if str((item.get("productData") or {}).get("productId")) == str(entry["product_id"]):
            return item
    return None


class Xtra:
    def __init__(
        self,
        *,
        api_key: Credential,
        session_cookie: Credential = None,
        place_id: Credential = None,
        session: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._session_cookie = session_cookie
        self._place_id = place_id
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Xtra:
        if self._session is None:
            self._session = _make_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.aclose()
            self._session = None

    def _headers(self, *, authenticated: bool) -> dict[str, str]:
        """Mimic the browser closely enough to satisfy the gateway.

        The cookie is set as a raw header rather than through a cookie jar so
        the request carries exactly one cookie and nothing the session picked
        up elsewhere.
        """
        headers = {
            "accept": "*/*",
            "accept-language": "nl,en-US;q=0.9,en;q=0.8",
            "origin": "https://www.colruyt.be",
            "referer": "https://www.colruyt.be/",
            "user-agent": BROWSER_UA,
            "x-cg-apikey": resolve(self._api_key, "XTRA_API_KEY"),
        }
        if authenticated:
            cookie = resolve(self._session_cookie, "XTRA_SESSION_COOKIE")
            headers["cookie"] = f"clpbff_session={cookie}"
        return headers

    def _list_params(self) -> dict[str, Any]:
        return {
            "limit": 255,
            "offset": 0,
            "sort": "createdAt desc",
            "placeId": resolve(self._place_id, "XTRA_PLACE_ID"),
            "lang": "nl",
            "prs": "true",
        }

    async def _call(self, method: str, url: str, *, authenticated: bool = True, **kwargs: Any):
        if self._session is None:
            raise RuntimeError("Use Xtra as an async context manager, or pass a session.")
        return await _request(
            self._session,
            method,
            url,
            headers=self._headers(authenticated=authenticated),
            auth_expired_message=_EXPIRED,
            **kwargs,
        )

    async def fetch_list(self, *, include_completed: bool = False) -> dict:
        """Read the shopping list along with which list it actually is.

        The account can hold more than one list and the response names the one
        being read, so a mismatch with what the Xtra app shows is diagnosable
        instead of looking like items going missing.
        """
        payload = await self._call("GET", f"{BFF}/latest-shopping-list", params=self._list_params())
        items = [_normalise(i) for i in _unwrap(payload)]
        if not include_completed:
            items = [i for i in items if not i["completed"]]
        model = (payload or {}).get("getListModel") or {}
        return {
            "items": items,
            "list_id": model.get("id"),
            "list_name": model.get("name"),
            "shared": bool(model.get("isShared")),
        }

    async def search_products(self, term: str, *, limit: int = 8) -> list[dict]:
        """Search the Colruyt catalogue by free text.

        The search term parameter is `searchTerm`; other plausible names are
        silently ignored by the gateway and return the unfiltered catalogue, so
        it must not be renamed casually. Needs no session — only the API key.
        """
        payload = await self._call(
            "GET",
            SEARCH,
            authenticated=False,
            params={
                "placeId": resolve(self._place_id, "XTRA_PLACE_ID"),
                "searchTerm": term,
                "size": max(1, limit),
            },
        )
        products = (payload or {}).get("products") or []
        return [_normalise_product(p) for p in products[:limit]]

    async def add_items(self, entries: list[dict]) -> dict:
        """Add entries to the list, reactivating anything that was ticked off.

        Each entry needs a `description` and a `product_id` (a
        technicalArticleNumber); `quantity` is optional. The endpoint rejects an
        entry without a product with an empty-bodied 422, so that is refused
        here before the request rather than surfaced as an unexplained failure.
        The description is only used to match the response — the stored line
        carries the product's own name.

        `add-items-to-list` is idempotent per product and ignores completion:
        adding a product already on the list — even one ticked off — leaves the
        existing line's `completedAt` untouched and only bumps the quantity.
        Left alone that makes "add the bananas" a silent no-op when a completed
        banana line is still there. No API flips an item's ticked-off state, so
        a still-completed product is reactivated by removing its line first and
        letting the add recreate it.

        Returns ``{"added": [...], "reactivated": [...]}``.
        """
        free_text = [e.get("description") for e in entries if not e.get("product_id")]
        if free_text:
            raise ValueError(
                "the shopping list only takes catalogue products; these entries have no "
                f"product_id: {', '.join(repr(d) for d in free_text)}. "
                "Find one with search_products()."
            )

        completed_by_product: dict[str, dict] = {}
        for item in await self._fetch_raw_items():
            if item.get("completedAt") is None:
                continue
            product_id = (item.get("productData") or {}).get("productId")
            if product_id is not None:
                completed_by_product[str(product_id)] = item

        reactivated_ids: set[str] = set()
        for entry in entries:
            product_id = entry.get("product_id")
            if product_id is None:
                continue
            existing = completed_by_product.get(str(product_id))
            if existing is not None:
                await self.remove_item(existing["id"])
                reactivated_ids.add(str(product_id))

        payload = await self._call(
            "POST", f"{BFF}/add-items-to-list", json={"items": [_build_entry(e) for e in entries]}
        )
        full_list = _unwrap(payload)

        added: list[dict] = []
        reactivated: list[dict] = []
        for entry in entries:
            target = _match_entry(full_list, entry)
            if target is None:
                continue
            product_id = entry.get("product_id")
            if product_id is not None and str(product_id) in reactivated_ids:
                reactivated.append(_normalise(target))
            else:
                added.append(_normalise(target))
        return {"added": added, "reactivated": reactivated}

    async def remove_item(self, item_id: str) -> None:
        await self._call("DELETE", f"{BFF}/remove-item-from-list/{item_id}")

    async def _fetch_raw_items(self) -> list[dict]:
        payload = await self._call("GET", f"{BFF}/latest-shopping-list", params=self._list_params())
        return _unwrap(payload)
