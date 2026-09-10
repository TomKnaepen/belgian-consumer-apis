"""The CLI layer: argument wiring, exit codes and the non-JSON rendering."""

import argparse
import json

import httpx
import pytest
import respx
from fixtures import (
    COMPLETED_BANANA,
    FRESH_BANANA,
    FRESH_MILK,
    MONIZZE_BALANCES,
    PLUXEE_CARDS,
    SEARCH_RESPONSE,
    add_response,
    jwt,
    list_response,
)

from beapi import TokenStore
from beapi.cli.main import _parser, run_monizze, run_pluxee, run_xtra
from beapi.monizze import BALANCES_URL
from beapi.pluxee import CARDS_URL, TOKEN_URL
from beapi.xtra import BFF, SEARCH

LIST_URL = f"{BFF}/latest-shopping-list"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("XTRA_API_KEY", "key-123")
    monkeypatch.setenv("XTRA_SESSION_COOKIE", "cookie-one")
    monkeypatch.setenv("XTRA_PLACE_ID", "0000")
    monkeypatch.setenv("MONIZZE_TOKEN", jwt(30))
    monkeypatch.setenv("PLUXEE_CLIENT_ID", "cid")
    monkeypatch.setenv("PLUXEE_SUBSCRIPTION_KEY", "skey")
    monkeypatch.setenv("PLUXEE_TOKEN_FILE", str(tmp_path / "pluxee.json"))
    monkeypatch.setenv("PLUXEE_USER", "alice")
    for absent in ("MONIZZE_TOKEN_FILE", "MONIZZE_USER"):
        monkeypatch.delenv(absent, raising=False)
    return tmp_path


@pytest.fixture
def pluxee_store(env):
    store = TokenStore(env / "pluxee.json")
    store.set("alice", "seed-token")
    return store


def _leaves(parser):
    subparsers = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subparsers:
        yield parser
        return
    for action in subparsers:
        for child in action.choices.values():
            yield from _leaves(child)


@pytest.mark.parametrize("leaf", list(_leaves(_parser(None))), ids=lambda p: p.prog)
def test_every_verb_accepts_json_after_itself(leaf):
    """`xtra ls --json` is the form the README and the HA sensors use."""
    assert "--json" in {opt for action in leaf._actions for opt in action.option_strings}


@respx.mock
def test_json_flag_is_accepted_on_either_side_of_the_verb(env, capsys):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([FRESH_MILK])))

    assert run_xtra(["ls", "--json"]) == 0
    trailing = json.loads(capsys.readouterr().out)
    assert run_xtra(["--json", "ls"]) == 0
    leading = json.loads(capsys.readouterr().out)

    assert trailing == leading
    assert [i["description"] for i in trailing["items"]] == ["melk"]


@respx.mock
def test_ls_renders_one_line_per_open_item(env, capsys):
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json=list_response([FRESH_MILK, COMPLETED_BANANA]))
    )
    assert run_xtra(["ls"]) == 0
    assert capsys.readouterr().out.splitlines() == ["  melk  [aaaa1111]"]


@respx.mock
def test_ls_all_marks_the_ticked_off_items(env, capsys):
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json=list_response([FRESH_MILK, COMPLETED_BANANA]))
    )
    assert run_xtra(["ls", "--all"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "  melk  [aaaa1111]",
        f"x BONI bananen  [{COMPLETED_BANANA['id']}]",
    ]


@respx.mock
def test_add_reports_what_the_response_confirmed(env, capsys):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    add = respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_MILK]))
    )
    assert run_xtra(["add", "melk", "--product-id", "12345"]) == 0
    assert json.loads(add.calls.last.request.read())["items"][0]["description"] == "melk"
    assert capsys.readouterr().out.strip() == "added melk"


@respx.mock
def test_add_joins_a_multi_word_description(env):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    add = respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_MILK]))
    )
    run_xtra(["add", "zes", "grote", "eieren", "--product-id", "12345"])
    entry = json.loads(add.calls.last.request.read())["items"][0]
    assert entry["description"] == "zes grote eieren"


@respx.mock
def test_add_carries_the_quantity_with_a_product_id(env):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    add = respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_MILK]))
    )
    run_xtra(["add", "melk", "--product-id", "12345", "--quantity", "2"])
    entry = json.loads(add.calls.last.request.read())["items"][0]
    assert entry["productData"] == {"productId": "12345", "quantity": 2, "unitCode": "P"}


def _add_routes():
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([])))
    return respx.post(f"{BFF}/add-items-to-list").mock(
        return_value=httpx.Response(200, json=add_response([FRESH_BANANA]))
    )


@respx.mock
def test_add_without_a_product_id_takes_the_best_match_under_yes(env, capsys):
    """The endpoint rejects free text, so a bare description is matched first."""
    add = _add_routes()
    assert run_xtra(["add", "bananen", "--yes"]) == 0
    assert json.loads(add.calls.last.request.read())["items"][0]["productData"] == {
        "productId": "29013",
        "quantity": 1,
        "unitCode": "P",
    }
    assert "matched 29013" in capsys.readouterr().err


@respx.mock
def test_add_asks_before_taking_the_match(env, capsys, monkeypatch):
    add = _add_routes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert run_xtra(["add", "bananen"]) == 0
    assert add.called
    assert "best match: 29013" in capsys.readouterr().err


@respx.mock
def test_a_declined_match_adds_nothing_and_exits_one(env, monkeypatch):
    add = _add_routes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    with pytest.raises(SystemExit) as exit_:
        run_xtra(["add", "bananen"])
    assert exit_.value.code == 1
    assert not add.called


@respx.mock
def test_a_non_interactive_run_without_yes_refuses_to_guess(env, capsys):
    """Home Assistant and agents get an error naming --yes, not a silent pick."""
    add = _add_routes()
    with pytest.raises(SystemExit) as exit_:
        run_xtra(["add", "bananen"])
    assert exit_.value.code == 2
    assert not add.called
    assert "--yes" in capsys.readouterr().err


@respx.mock
def test_add_of_something_the_catalogue_lacks_exits_one(env, capsys):
    add = _add_routes()
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={"products": []}))
    with pytest.raises(SystemExit) as exit_:
        run_xtra(["add", "vliegend", "tapijt", "--yes"])
    assert exit_.value.code == 1
    assert not add.called
    assert "no catalogue product matched 'vliegend tapijt'" in capsys.readouterr().err


@respx.mock
def test_rm_deletes_the_given_id(env, capsys):
    removal = respx.delete(f"{BFF}/remove-item-from-list/aaaa1111").mock(
        return_value=httpx.Response(204)
    )
    assert run_xtra(["rm", "aaaa1111"]) == 0
    assert removal.called
    assert capsys.readouterr().out.strip() == "removed aaaa1111"


@respx.mock
def test_search_renders_price_and_product_id(env, capsys):
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))
    assert run_xtra(["search", "bananen", "--limit", "5"]) == 0
    assert capsys.readouterr().out.strip() == "29013  BONI bananen ±1kg  €2.29"


@respx.mock
def test_login_reports_the_list_the_cookie_reaches(env, capsys):
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=list_response([FRESH_MILK])))
    assert run_xtra(["login"]) == 0
    assert "session works — 1 item(s)" in capsys.readouterr().out


def test_login_without_a_cookie_prints_the_capture_steps(env, monkeypatch, capsys):
    monkeypatch.delenv("XTRA_SESSION_COOKIE")
    with pytest.raises(SystemExit) as exit_:
        run_xtra(["login"])
    assert exit_.value.code == 2
    assert "clpbff_session" in capsys.readouterr().err


def test_a_missing_credential_exits_one_and_names_itself(env, monkeypatch, capsys):
    monkeypatch.delenv("XTRA_PLACE_ID")
    assert run_xtra(["ls"]) == 1
    assert capsys.readouterr().err.startswith("CredentialMissing: XTRA_PLACE_ID")


@respx.mock
def test_a_rejected_cookie_exits_one_rather_than_raising(env, capsys):
    respx.get(LIST_URL).mock(return_value=httpx.Response(401))
    assert run_xtra(["ls"]) == 1
    assert capsys.readouterr().err.startswith("AuthExpired:")


@respx.mock
def test_monizze_balance_carries_the_token_countdown(env, capsys):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    assert run_monizze(["balance"]) == 0
    assert capsys.readouterr().out.startswith("meal: €125.99  (token 29d left)")


@respx.mock
def test_monizze_balance_takes_the_voucher_type(env, capsys):
    respx.get(BALANCES_URL).mock(return_value=httpx.Response(200, json=MONIZZE_BALANCES))
    assert run_monizze(["balance", "eco", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["balance"] == 40.0


@respx.mock
def test_monizze_token_needs_no_network(env, capsys):
    """No route is registered: any request would fail the run."""
    assert run_monizze(["token"]) == 0
    assert "29d left" in capsys.readouterr().out


@respx.mock
def test_pluxee_get_persists_the_rotated_token(pluxee_store, capsys):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"refresh_token": "rotated-token", "access_token": "access-token"}
        )
    )
    respx.get(CARDS_URL).mock(return_value=httpx.Response(200, json=PLUXEE_CARDS))

    assert run_pluxee(["get", "lunch"]) == 0

    assert capsys.readouterr().out.strip() == "lunch: €170.00  (expires 2027-03-31)"
    assert pluxee_store.get("alice") == "rotated-token"


@respx.mock
def test_pluxee_without_a_seeded_token_exits_one(env, capsys):
    assert run_pluxee(["get"]) == 1
    assert capsys.readouterr().err.startswith("CredentialMissing:")
