#!/usr/bin/env python3
"""Fetch the voucher balances and push them into Home Assistant as states.

Run on a schedule outside HA. Separating the two rates matters: the providers
are polled slowly (daily is plenty for a balance), while the push repeats often
enough that a restarted HA is never showing `unknown` for long. That only works
because the push reads the stored result and never calls a provider.

    ./push_balances.py --poll --push     # daily
    ./push_balances.py --push            # every 15 minutes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from beapi import BeapiError, Monizze, Pluxee, TokenStore, from_env

STATE_FILE = Path(os.environ.get("VOUCHER_STATE_FILE", "voucher_state.json"))
HA_URL = os.environ.get("HOMEASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_TOKEN", "")

SENSORS = {
    "sensor.pluxee_meal_balance": ("pluxee", "lunch"),
    "sensor.monizze_meal_balance": ("monizze", "meal"),
}


async def _read(provider: str, voucher: str) -> dict:
    if provider == "pluxee":
        store = TokenStore(os.environ.get("PLUXEE_TOKEN_FILE", ".pluxee_tokens.json"))
        async with Pluxee.from_store(
            store,
            os.environ.get("PLUXEE_USER", "default"),
            client_id=from_env("PLUXEE_CLIENT_ID"),
            subscription_key=from_env("PLUXEE_SUBSCRIPTION_KEY"),
        ) as client:
            return await client.balance(voucher)

    async with Monizze(token=from_env("MONIZZE_TOKEN")) as client:
        balance = await client.balance(voucher)
        expires_at, days_left = client.expiry()
    return {"balance": balance, "token_expires_at": expires_at, "token_days_left": days_left}


async def poll() -> dict:
    """Read every provider, keeping the previous value for any that fails.

    A failed read must not overwrite a good balance with nothing: the number is
    still roughly right, and `fetched_at` on the pushed state says how old it
    is. Only the error is new information.
    """
    state = _load_state()
    for entity_id, (provider, voucher) in SENSORS.items():
        previous = state.get(entity_id, {})
        try:
            result = await _read(provider, voucher)
        except BeapiError as exc:
            state[entity_id] = {**previous, "error": f"{type(exc).__name__}: {exc}"}
            continue
        state[entity_id] = {
            **result,
            "error": "",
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    _save_state(state)
    return state


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


async def push(state: dict) -> None:
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as http:
        for entity_id, data in state.items():
            balance = data.get("balance")
            await http.post(
                f"{HA_URL}/api/states/{entity_id}",
                headers=headers,
                json={
                    "state": "unavailable" if balance is None else balance,
                    "attributes": {
                        "unit_of_measurement": "€",
                        "device_class": "monetary",
                        **{k: v for k, v in data.items() if k != "balance"},
                    },
                },
            )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll", action="store_true", help="read the providers")
    parser.add_argument("--push", action="store_true", help="push stored state to HA")
    args = parser.parse_args()

    state = await poll() if args.poll else _load_state()
    if args.push:
        await push(state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
