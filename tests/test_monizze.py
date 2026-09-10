from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fixtures import MONIZZE_BALANCES, jwt

from beapi import AuthExpired, Monizze
from beapi.monizze import BALANCES_URL, token_expiry


@respx.mock
async def test_meal_balance_reads_the_emv_bucket(monizze):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    assert await monizze.balance() == 125.99


@respx.mock
async def test_eco_balance_reads_its_own_bucket(monizze):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    assert await monizze.balance("eco") == 40.0


@respx.mock
async def test_absent_voucher_type_reads_as_zero_not_an_error(monizze):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    assert await monizze.balance("gift") == 0.0


@respx.mock
async def test_a_bare_token_is_given_its_bearer_prefix(session):
    route = respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    await Monizze(token="eyJhbGci.payload.sig", session=session).balances()
    assert route.calls.last.request.headers["authorization"] == "Bearer eyJhbGci.payload.sig"


@respx.mock
async def test_rejected_token_raises_auth_expired(monizze):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(AuthExpired):
        await monizze.balances()


def test_token_expiry_decodes_the_exp_claim():
    date, days_left = token_expiry(jwt(30))
    assert days_left in (29, 30)
    assert date == (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")


def test_an_undecodable_token_is_unknown_rather_than_expired():
    """A parse failure says nothing about the token's validity."""
    assert token_expiry("not-a-jwt") == ("unknown", -1)
