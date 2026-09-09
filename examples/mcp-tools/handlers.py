"""Bind the tool definitions in xtra-tools.json to the client. Example, not a module."""

from collections.abc import Awaitable, Callable
from typing import Any

from beapi import AuthExpired, BeapiError, Xtra


def build_handlers(xtra: Xtra) -> dict[str, Callable[[dict], Awaitable[Any]]]:
    async def search(args: dict) -> Any:
        return await xtra.search_products(args["term"], limit=min(args.get("limit", 8), 25))

    async def list_items(args: dict) -> Any:
        return await xtra.fetch_list(include_completed=args.get("include_completed", False))

    async def add_items(args: dict) -> Any:
        return await xtra.add_items(args["items"])

    async def remove_item(args: dict) -> Any:
        await xtra.remove_item(args["item_id"])
        return {"removed": args["item_id"]}

    handlers = {
        "xtra_search_products": search,
        "xtra_list_items": list_items,
        "xtra_add_items": add_items,
        "xtra_remove_item": remove_item,
    }
    return {name: _as_tool_result(fn) for name, fn in handlers.items()}


def _as_tool_result(fn: Callable[[dict], Awaitable[Any]]) -> Callable[[dict], Awaitable[Any]]:
    """Hand the model a readable error instead of unwinding the tool loop.

    An AuthExpired reaching the model as a stack trace produces a confident
    apology about the shopping list being empty. Told what actually happened, it
    relays the one thing a human can act on.
    """

    async def call(args: dict) -> Any:
        try:
            return await fn(args)
        except AuthExpired as exc:
            return {"error": f"Colruyt session expired: {exc}"}
        except BeapiError as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    return call
