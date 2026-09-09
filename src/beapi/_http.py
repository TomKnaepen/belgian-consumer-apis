"""Shared transport: one client factory and one status-to-exception mapping."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import AuthExpired, UpstreamError

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def client(**kwargs: Any) -> httpx.AsyncClient:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    kwargs.setdefault("follow_redirects", True)
    return httpx.AsyncClient(**kwargs)


async def request(
    session: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    auth_expired_message: str,
    **kwargs: Any,
) -> Any:
    try:
        response = await session.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{method} {url} failed: {exc}") from exc

    if response.status_code in (401, 403):
        raise AuthExpired(auth_expired_message)
    if response.status_code >= 400:
        raise UpstreamError(
            f"{url} returned {response.status_code}: {response.text[:200]}",
            status=response.status_code,
            body=response.text,
        )
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError(f"{url} did not return JSON: {response.text[:200]}") from exc
