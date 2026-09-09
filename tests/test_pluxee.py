import httpx
import pytest
import respx
from fixtures import PLUXEE_CARDS

from beapi import AuthExpired, ContractError, Pluxee, TokenStore, UpstreamError
from beapi.pluxee import CARDS_URL, TOKEN_URL, extract_balance


def _token_response(refresh="rotated-token", access="access-token"):
    return httpx.Response(200, json={"refresh_token": refresh, "access_token": access})


@respx.mock
async def test_lunch_balance_applies_the_amount_exponent(pluxee):
    respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(CARDS_URL).mock(return_value=httpx.Response(200, json=PLUXEE_CARDS))
    assert await pluxee.balance("lunch") == {"balance": 170.0, "expiry": "2027-03-31"}


@respx.mock
async def test_eco_balance_without_an_expiring_bucket_reports_no_expiry(pluxee):
    respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(CARDS_URL).mock(return_value=httpx.Response(200, json=PLUXEE_CARDS))
    assert await pluxee.balance("eco") == {"balance": 250.5, "expiry": ""}


@respx.mock
async def test_the_rotated_token_is_persisted_before_the_cards_call(pluxee):
    """The exchange burns the old token, so its replacement must be stored first."""
    seen_rotations_at_cards_time = []
    respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(CARDS_URL).mock(
        side_effect=lambda request: (
            seen_rotations_at_cards_time.extend(pluxee.rotations),
            httpx.Response(200, json=PLUXEE_CARDS),
        )[1]
    )

    await pluxee.balance("lunch")

    assert pluxee.rotations == ["rotated-token"]
    assert seen_rotations_at_cards_time == ["rotated-token"]


@respx.mock
async def test_an_unchanged_refresh_token_is_not_rewritten(pluxee):
    respx.post(TOKEN_URL).mock(return_value=_token_response(refresh="seed-token"))
    respx.get(CARDS_URL).mock(return_value=httpx.Response(200, json=PLUXEE_CARDS))
    await pluxee.balance("lunch")
    assert pluxee.rotations == []


@respx.mock
async def test_a_spent_refresh_token_raises_auth_expired(pluxee):
    """OAuth carries invalid_grant on a 400, not the 401 that usually means expiry."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(AuthExpired, match="mobile-app login"):
        await pluxee.balance()


@respx.mock
async def test_a_malformed_token_request_is_not_reported_as_an_expiry(pluxee):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_request"})
    )
    with pytest.raises(UpstreamError):
        await pluxee.balance()


@respx.mock
async def test_a_token_response_without_an_access_token_is_a_contract_error(pluxee):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"refresh_token": "x"}))
    with pytest.raises(ContractError):
        await pluxee.balance()


@respx.mock
async def test_from_store_round_trips_the_rotation_to_disk(session, tmp_path):
    store = TokenStore(tmp_path / "pluxee.json")
    store.set("alice", "seed-token")
    respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(CARDS_URL).mock(return_value=httpx.Response(200, json=PLUXEE_CARDS))

    client = Pluxee.from_store(
        store, "alice", client_id="cid", subscription_key="skey", session=session
    )
    await client.balance("lunch")

    assert store.get("alice") == "rotated-token"


def test_an_unknown_pass_type_is_a_contract_error():
    with pytest.raises(ContractError, match="W9"):
        extract_balance(PLUXEE_CARDS, "W9")
