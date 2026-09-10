import json

import httpx
import pytest
import respx
from fixtures import (
    COMPLETED_BANANA,
    FRESH_BANANA,
    FRESH_MILK,
    SEARCH_RESPONSE,
    add_response,
    list_response,
)

from beapi import AuthExpired, ContractError
from beapi.xtra import BFF, SEARCH

LIST_URL = f"{BFF}/latest-shopping-list"


@respx.mock
async def test_fetch_list_hides_completed_and_names_the_list(xtra):
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json=list_response([COMPLETED_BANANA, FRESH_MILK]))
    )
    listing = await xtra.fetch_list()
    assert [i["description"] for i in listing["items"]] == ["melk"]
    assert listing["list_name"] == "My shopping list on clp website"
    assert listing["shared"] is True


@respx.mock
async def test_fetch_list_converts_epoch_created_at_to_iso(xtra):
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json=list_response([FRESH_MILK, COMPLETED_BANANA]))
    )
    listing = await xtra.fetch_list(include_completed=True)
    banana = next(i for i in listing["items"] if i["product_id"] == "29013")
    assert banana["created_at"] == "2025-07-27T20:18:06Z"


@respx.mock
async def test_unknown_response_shape_raises_instead_of_reading_as_empty(xtra):
    """An upstream rename must never surface as "your list is empty"."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"unexpected": {}}))
    with pytest.raises(ContractError):
        await xtra.fetch_list()


@respx.mock
async def test_rejected_cookie_raises_auth_expired(xtra):
    respx.get(LIST_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(AuthExpired, match="clpbff_session"):
        await xtra.fetch_list()


@respx.mock
async def test_add_reactivates_a_ticked_off_product_by_removing_it_first(xtra):
    listing = respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json=list_response([COMPLETED_BANANA]))
    )
    removal = respx.delete(f"{BFF}/remove-item-from-list/{COMPLETED_BANANA['id']}").mock(
        return_value=httpx.Response(204)
    )
    add = respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_BANANA]))
    )

    result = await xtra.add_items([{"description": "BONI bananen", "product_id": "29013"}])

    assert listing.called and removal.called and add.called
    assert result["added"] == []
    assert [i["id"] for i in result["reactivated"]] == [FRESH_BANANA["id"]]


@respx.mock
async def test_add_of_an_absent_product_does_not_remove_anything(xtra):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    removal = respx.delete(url__startswith=f"{BFF}/remove-item-from-list/")
    respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_MILK]))
    )

    result = await xtra.add_items([{"description": "melk", "product_id": "12345"}])

    assert not removal.called
    assert [i["description"] for i in result["added"]] == ["melk"]
    assert result["reactivated"] == []


@respx.mock
async def test_add_sends_a_client_minted_id_and_product_data(xtra):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    add = respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_BANANA]))
    )

    await xtra.add_items([{"description": "BONI bananen", "product_id": "29013", "quantity": 3}])

    entry = json.loads(add.calls.last.request.read())["items"][0]
    assert entry["id"] and entry["completedAt"] is None
    assert entry["productData"] == {"productId": "29013", "quantity": 3, "unitCode": "P"}


@respx.mock
async def test_search_uses_searchTerm_and_sends_no_cookie(xtra):
    """Renaming the parameter silently returns the unfiltered catalogue."""
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))

    products = await xtra.search_products("bananen", limit=5)

    request = route.calls.last.request
    assert request.url.params["searchTerm"] == "bananen"
    assert request.url.params["size"] == "5"
    assert "cookie" not in request.headers
    assert request.headers["x-cg-apikey"] == "key-123"
    assert products[0]["long_name"] == "BONI bananen ±1kg"
    assert products[0]["name"] == "bananen"


async def test_add_refuses_a_free_text_entry_before_calling(xtra):
    """The BFF answers an entry without productData with an empty-bodied 422."""
    with pytest.raises(ValueError, match="product_id"):
        await xtra.add_items([{"description": "melk"}])
