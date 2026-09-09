"""Command line front end.

`beapi <provider> <verb>`, plus `xtra`, `monizze` and `pluxee` as direct
aliases. Every credential comes from the environment and is read at call time.
Every command prints JSON under `--json`, so the CLI is usable as the data
source for a Home Assistant command_line sensor or a shell script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from .. import Monizze, Pluxee, TokenStore, Xtra
from ..credentials import from_env
from ..errors import BeapiError

ENV_HELP = """\
Credentials are read from the environment:

  Colruyt Xtra   XTRA_API_KEY, XTRA_SESSION_COOKIE, XTRA_PLACE_ID
  Monizze        MONIZZE_TOKEN, or MONIZZE_TOKEN_FILE + MONIZZE_USER
  Pluxee         PLUXEE_CLIENT_ID, PLUXEE_SUBSCRIPTION_KEY,
                 PLUXEE_TOKEN_FILE + PLUXEE_USER

None of them ship with a default. See docs/reverse-engineering/ for how to
obtain each one.
"""


def _emit(data: Any, as_json: bool, plain: Callable[[Any], str] | None = None) -> None:
    if as_json or plain is None:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(plain(data))


def _xtra() -> Xtra:
    return Xtra(
        api_key=from_env("XTRA_API_KEY"),
        session_cookie=from_env("XTRA_SESSION_COOKIE"),
        place_id=from_env("XTRA_PLACE_ID"),
    )


def _monizze() -> Monizze:
    if os.environ.get("MONIZZE_TOKEN"):
        return Monizze(token=from_env("MONIZZE_TOKEN"))
    store = TokenStore(os.environ.get("MONIZZE_TOKEN_FILE", ".monizze_tokens.json"))
    return Monizze(token=store.reader(os.environ.get("MONIZZE_USER", "default")))


def _pluxee() -> Pluxee:
    store = TokenStore(os.environ.get("PLUXEE_TOKEN_FILE", ".pluxee_tokens.json"))
    return Pluxee.from_store(
        store,
        os.environ.get("PLUXEE_USER", "default"),
        client_id=from_env("PLUXEE_CLIENT_ID"),
        subscription_key=from_env("PLUXEE_SUBSCRIPTION_KEY"),
    )


async def _xtra_ls(args: argparse.Namespace) -> None:
    async with _xtra() as client:
        listing = await client.fetch_list(include_completed=args.all)
    _emit(
        listing,
        args.json,
        lambda d: "\n".join(
            f"{'x' if i['completed'] else ' '} {i['description']}"
            + (f" ×{i['quantity']}" if (i.get("quantity") or 1) > 1 else "")
            + f"  [{i['id']}]"
            for i in d["items"]
        )
        or "(list is empty)",
    )


async def _xtra_add(args: argparse.Namespace) -> None:
    entry: dict[str, Any] = {"description": " ".join(args.description)}
    if args.product_id:
        entry["product_id"] = args.product_id
    if args.quantity:
        entry["quantity"] = args.quantity
    async with _xtra() as client:
        result = await client.add_items([entry])
    _emit(
        result,
        args.json,
        lambda d: "\n".join(
            [f"added {i['description']}" for i in d["added"]]
            + [f"reactivated {i['description']}" for i in d["reactivated"]]
        )
        or "nothing matched in the response",
    )


async def _xtra_rm(args: argparse.Namespace) -> None:
    async with _xtra() as client:
        await client.remove_item(args.item_id)
    _emit({"removed": args.item_id}, args.json, lambda d: f"removed {d['removed']}")


async def _xtra_search(args: argparse.Namespace) -> None:
    async with _xtra() as client:
        products = await client.search_products(" ".join(args.term), limit=args.limit)
    _emit(
        products,
        args.json,
        lambda d: "\n".join(
            f"{p['product_id']}  {p['long_name'] or p['name']}  "
            f"€{p['price']}{'  (promo)' if p['in_promo'] else ''}"
            for p in d
        )
        or "no products matched",
    )


async def _xtra_login(args: argparse.Namespace) -> None:
    """Verify the configured cookie rather than perform a login.

    Colruyt's login is an interactive browser flow behind the BFF; there is no
    credential this tool could exchange for a session. The useful thing a CLI
    can do is tell you whether what you pasted works.
    """
    guidance = (
        "Colruyt has no headless login. Obtain the session cookie by hand:\n"
        "  1. Sign in at https://www.colruyt.be\n"
        "  2. DevTools -> Application -> Cookies -> www.colruyt.be\n"
        "  3. Copy the value of clpbff_session into XTRA_SESSION_COOKIE\n"
        "  4. Copy the x-cg-apikey request header into XTRA_API_KEY\n"
        "The cookie lasts roughly two months.\n"
    )
    if not os.environ.get("XTRA_SESSION_COOKIE"):
        print(guidance, file=sys.stderr)
        raise SystemExit(2)
    async with _xtra() as client:
        listing = await client.fetch_list()
    _emit(
        {"ok": True, "list_name": listing["list_name"], "items": len(listing["items"])},
        args.json,
        lambda d: f"session works — {d['items']} item(s) on {d['list_name']!r}",
    )


async def _monizze_balance(args: argparse.Namespace) -> None:
    async with _monizze() as client:
        value = await client.balance(args.voucher)
    expires_at, days_left = _monizze().expiry()
    _emit(
        {
            "balance": value,
            "voucher": args.voucher,
            "token_expires_at": expires_at,
            "token_days_left": days_left,
        },
        args.json,
        lambda d: f"{d['voucher']}: €{d['balance']:.2f}  (token {d['token_days_left']}d left)",
    )


async def _monizze_token(args: argparse.Namespace) -> None:
    expires_at, days_left = _monizze().expiry()
    _emit(
        {"token_expires_at": expires_at, "token_days_left": days_left},
        args.json,
        lambda d: f"token expires {d['token_expires_at']} ({d['token_days_left']}d left)",
    )


async def _pluxee_get(args: argparse.Namespace) -> None:
    async with _pluxee() as client:
        result = await client.balance(args.voucher)
    _emit(
        {"voucher": args.voucher, **result},
        args.json,
        lambda d: f"{d['voucher']}: €{d['balance']:.2f}"
        + (f"  (expires {d['expiry']})" if d["expiry"] else ""),
    )


async def _pluxee_cards(args: argparse.Namespace) -> None:
    async with _pluxee() as client:
        _emit(await client.cards(), True)


def _add_xtra(sub: argparse._SubParsersAction) -> None:
    ls = sub.add_parser("ls", help="show the shopping list")
    ls.add_argument("--all", action="store_true", help="include ticked-off items")
    ls.set_defaults(run=_xtra_ls)

    add = sub.add_parser("add", help="add an item")
    add.add_argument("description", nargs="+")
    add.add_argument("--product-id", help="Colruyt technical article number")
    add.add_argument("--quantity", type=int)
    add.set_defaults(run=_xtra_add)

    rm = sub.add_parser("rm", help="remove an item by id")
    rm.add_argument("item_id")
    rm.set_defaults(run=_xtra_rm)

    search = sub.add_parser("search", help="search the catalogue (needs no session)")
    search.add_argument("term", nargs="+")
    search.add_argument("--limit", type=int, default=8)
    search.set_defaults(run=_xtra_search)

    login = sub.add_parser("login", help="check the configured session cookie")
    login.set_defaults(run=_xtra_login)


def _add_monizze(sub: argparse._SubParsersAction) -> None:
    balance = sub.add_parser("balance", help="read a voucher balance")
    balance.add_argument("voucher", nargs="?", default="meal",
                         choices=["meal", "eco", "gift", "consumption"])
    balance.set_defaults(run=_monizze_balance)

    token = sub.add_parser("token", help="show when the stored token expires")
    token.set_defaults(run=_monizze_token)


def _add_pluxee(sub: argparse._SubParsersAction) -> None:
    get = sub.add_parser("get", help="read a voucher balance")
    get.add_argument("voucher", nargs="?", default="lunch",
                     choices=["lunch", "eco", "gift", "sport"])
    get.set_defaults(run=_pluxee_get)

    cards = sub.add_parser("cards", help="dump the raw cards response")
    cards.set_defaults(run=_pluxee_cards)


PROVIDERS: dict[str, Callable[[argparse._SubParsersAction], None]] = {
    "xtra": _add_xtra,
    "monizze": _add_monizze,
    "pluxee": _add_pluxee,
}


def _parser(provider: str | None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=provider or "beapi",
        description=__doc__.split("\n")[0],
        epilog=ENV_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    if provider is None:
        providers = parser.add_subparsers(dest="provider", required=True)
        for name, register in PROVIDERS.items():
            register(providers.add_parser(name).add_subparsers(dest="verb", required=True))
    else:
        PROVIDERS[provider](parser.add_subparsers(dest="verb", required=True))
    return parser


def _dispatch(provider: str | None, argv: list[str] | None = None) -> int:
    args = _parser(provider).parse_args(argv)
    try:
        asyncio.run(args.run(args))
    except BeapiError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def run(argv: list[str] | None = None) -> int:
    return _dispatch(None, argv)


def run_xtra(argv: list[str] | None = None) -> int:
    return _dispatch("xtra", argv)


def run_monizze(argv: list[str] | None = None) -> int:
    return _dispatch("monizze", argv)


def run_pluxee(argv: list[str] | None = None) -> int:
    return _dispatch("pluxee", argv)


if __name__ == "__main__":
    raise SystemExit(run())
