import pytest

from beapi import Monizze, Pluxee, Xtra
from beapi._http import client


@pytest.fixture
async def session():
    async with client() as http:
        yield http


@pytest.fixture
def xtra(session):
    return Xtra(api_key="key-123", session_cookie="cookie-one", place_id="0000", session=session)


@pytest.fixture
def monizze(session):
    return Monizze(token="Bearer test.token", session=session)


@pytest.fixture
def pluxee(session):
    rotations = []
    client_ = Pluxee(
        refresh_token="seed-token",
        client_id="cid",
        subscription_key="skey",
        on_rotate=rotations.append,
        session=session,
    )
    client_.rotations = rotations
    return client_
