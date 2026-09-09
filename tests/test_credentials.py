import os

import httpx
import pytest
import respx
from fixtures import SEARCH_RESPONSE

from beapi import Xtra
from beapi.credentials import TokenStore, resolve
from beapi.errors import CredentialMissing
from beapi.xtra import SEARCH


def test_a_missing_credential_names_itself():
    with pytest.raises(CredentialMissing, match="XTRA_API_KEY"):
        resolve("", "XTRA_API_KEY")


def test_whitespace_only_counts_as_missing():
    with pytest.raises(CredentialMissing):
        resolve("   ", "TOKEN")


@respx.mock
async def test_a_callable_credential_is_read_per_request(session):
    """The seam that keeps a re-pasted cookie from needing a restart."""
    keys = iter(["first-key", "second-key"])
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))
    client = Xtra(api_key=lambda: next(keys), place_id="0000", session=session)

    await client.search_products("a")
    await client.search_products("b")

    assert [c.request.headers["x-cg-apikey"] for c in route.calls] == ["first-key", "second-key"]


def test_token_store_writes_are_owner_only(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    store.set("Alice", "secret")
    assert store.get("alice") == "secret"
    assert oct(os.stat(store.path).st_mode)[-3:] == "600"


def test_token_store_treats_an_unreadable_file_as_empty(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text("{ not json")
    assert TokenStore(path).get("alice") == ""
