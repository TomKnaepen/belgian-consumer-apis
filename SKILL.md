---
name: belgian-consumer-apis
description: Read and write a Colruyt Xtra shopping list, and read Monizze and Pluxee meal-voucher balances, from Python or the command line. Use when a task involves Belgian groceries, a shopping list, or meal-voucher balances — or when working in this repository.
---

# belgian-consumer-apis

Three unofficial clients for Belgian consumer services that publish no API.
Everything is derived from the providers' own web and mobile traffic and can
break without notice.

## Choosing an entry point

| You want | Use |
|---|---|
| a shell command, a cron job, an HA `command_line` sensor | the CLI, with `--json` |
| to call this from an async application | the library |

## CLI

```bash
xtra ls [--all]                       # --all includes ticked-off items
xtra search <term> [--limit N]        # needs no session, only the API key
xtra add "<description>" [--yes] [--product-id ID] [--quantity N]
xtra rm <item-id>                     # id comes from `xtra ls`
xtra login                            # verify the configured cookie

monizze balance [meal|eco|gift|consumption]
monizze token                         # days left on the stored JWT

pluxee get [lunch|eco|gift|sport]
pluxee cards                          # raw response
```

`--json` on any command. Exit code 1 with the exception name on stderr for any
provider error. `beapi xtra ls` is the same as `xtra ls`.

## Library

```python
from beapi import Xtra, Monizze, Pluxee, TokenStore, from_env

async with Xtra(api_key=..., session_cookie=..., place_id=...) as xtra:
    listing = await xtra.fetch_list()            # {"items", "list_id", "list_name", "shared"}
    hits    = await xtra.search_products("melk", limit=5)
    result  = await xtra.add_items([{"description": "melk", "product_id": "12345"}])
    await xtra.remove_item(item_id)

async with Monizze(token=...) as monizze:
    await monizze.balance("meal")                # float
    monizze.expiry()                             # ("2026-11-02", 54)

async with Pluxee.from_store(store, "alice", client_id=..., subscription_key=...) as pluxee:
    await pluxee.balance("lunch")                # {"balance": 123.45, "expiry": "2028-01-31"}
```

All clients are async context managers. Pass an existing `httpx.AsyncClient` as
`session=` to share a connection pool; the client then does not close it.

## Rules that are easy to get wrong

**Credentials may be callables, and should be when config is live.** Every
credential argument takes a string *or* a zero-argument callable, resolved per
request. Resolving once at construction pins a rotated token or a re-pasted
cookie to its startup value:

```python
Xtra(api_key=lambda: config.XTRA_API_KEY, ...)      # picks up a change
Xtra(api_key=config.XTRA_API_KEY, ...)              # frozen at construction
```

**Only one process may hold a Pluxee refresh token.** It rotates on every
exchange and the old value dies at once. Do not seed two pollers, and do not
put a production token in CI.

**`AuthExpired` is never retryable.** It always means a human must supply a new
credential. `UpstreamError` is the retryable one. `ContractError` means the
response parsed but its shape is unknown — report it, do not paper over it.

**An empty result and a changed response shape are different.** The Xtra client
raises `ContractError` rather than returning an empty list when it cannot find
the item array, because "your shopping list is empty" is the one wrong answer
that sends someone to the shop with nothing.

**Xtra product search needs no session.** It keeps working after the shopping
list cookie has lapsed, so it is useless as a health check for the cookie —
`fetch_list` is the cheapest call that actually proves the session.

**The list takes catalogue products, not free text.** `add-items-to-list`
rejects an entry without `productData` with an empty-bodied 422, so `add_items`
refuses one before the request. The CLI searches for a bare description and
asks before adding the match — `--yes` for unattended callers, `--product-id`
to skip the search. The description you send is discarded when the product is
present: the stored line carries the product's own name, so an added item is
findable only by the client-minted id.

**Re-adding a ticked-off item is not a no-op here.** `add_items` deletes the
completed line and lets the add recreate it.

## Errors

```
BeapiError
├── CredentialMissing   a required credential resolved to empty
├── AuthExpired         rejected credential; a human must re-authenticate
├── UpstreamError       provider errored or was unreachable (has .status, .body)
└── ContractError       parsed, but the shape is not the one we know
```

## Working in this repository

- Source in `src/beapi/`, one module per provider plus `_http`, `credentials`,
  `errors`. The CLI is `src/beapi/cli/main.py`.
- Tests are offline, against `respx` mocks and the fixtures in
  `tests/fixtures.py`. `uv run pytest`. **Never add a test that calls a real
  provider** — for Pluxee it would rotate a live token out from under whoever
  owns it.
- Endpoint behaviour that is surprising belongs in
  `docs/reverse-engineering/<provider>.md`, not in a code comment.
- No credential ever gets a working default, including the gateway keys.
