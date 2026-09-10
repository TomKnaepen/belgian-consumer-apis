# belgian-consumer-apis

Unofficial Python clients for three Belgian consumer services that publish no
API: **Colruyt Xtra** (shopping list and product catalogue), **Monizze** and
**Pluxee** (meal-voucher balances).

Every endpoint here was derived from the traffic of the providers' own web and
mobile clients. Nothing is affiliated with, endorsed by, or supported by
Colruyt Group, Monizze or Pluxee, and any of it can break without notice.

## What you get

| | Capability |
|---|---|
| **Xtra** | read the shopping list, add and remove items, search the catalogue |
| **Monizze** | meal / eco / gift / consumption balances, token expiry |
| **Pluxee** | lunch / eco / gift / sport balances and their expiry dates |

Async clients (`httpx`), a CLI over the same code, and — in
[`docs/reverse-engineering/`](docs/reverse-engineering/) — the write-ups of how
each API was found, including the paths that turned out to be dead ends.

## Install

Not on PyPI — install from git.

```bash
uv add git+https://github.com/TomKnaepen/belgian-consumer-apis
# or: pip install git+https://github.com/TomKnaepen/belgian-consumer-apis
```

## CLI

```bash
xtra ls                          # the shopping list
xtra search bananen --limit 5
xtra add "bananen" --quantity 2
xtra rm 4f3c…                    # id from `xtra ls`
xtra login                       # verify the configured cookie

monizze balance                  # meal by default
monizze balance eco
monizze token                    # days left on the stored JWT

pluxee get lunch
pluxee get eco --json
```

Every command takes `--json`, which is what makes it usable as a Home Assistant
`command_line` sensor. `beapi xtra ls` is equivalent to `xtra ls`.

## Library

```python
import asyncio
from beapi import Xtra, from_env

async def main():
    async with Xtra(
        api_key=from_env("XTRA_API_KEY"),
        session_cookie=from_env("XTRA_SESSION_COOKIE"),
        place_id=from_env("XTRA_PLACE_ID"),
    ) as xtra:
        listing = await xtra.fetch_list()
        for item in listing["items"]:
            print(item["description"])

asyncio.run(main())
```

Every credential accepts a plain string **or a zero-argument callable**. Pass a
callable when your configuration can change while the process runs — it is
resolved per request, so a re-pasted cookie or a rotated token applies without
a restart.

```python
Xtra(api_key=lambda: settings.xtra_api_key, ...)
```

## Credentials

No credential ships with a default, including the API keys that are technically
public. You supply all of them:

| Provider | Environment | How to obtain |
|---|---|---|
| Xtra | `XTRA_API_KEY`, `XTRA_SESSION_COOKIE`, `XTRA_PLACE_ID` | [docs/reverse-engineering/xtra.md](docs/reverse-engineering/xtra.md) |
| Monizze | `MONIZZE_TOKEN`, or `MONIZZE_TOKEN_FILE` + `MONIZZE_USER` | [docs/reverse-engineering/monizze.md](docs/reverse-engineering/monizze.md) |
| Pluxee | `PLUXEE_CLIENT_ID`, `PLUXEE_SUBSCRIPTION_KEY`, `PLUXEE_TOKEN_FILE` + `PLUXEE_USER` | [docs/reverse-engineering/pluxee.md](docs/reverse-engineering/pluxee.md) |

Lifetimes differ and the failure modes follow from that:

- **Xtra** — an opaque session cookie, ~2 months, no refresh. Copy a new one
  from a logged-in browser. `AuthExpired` says exactly this.
- **Monizze** — a bearer JWT, ~2 months, no refresh reachable from outside the
  app. `monizze token` tells you how long you have.
- **Pluxee** — an OIDC refresh token that **rotates on every call**. The client
  hands you the replacement through `on_rotate` (or persists it for you via
  `TokenStore`) before it does anything else. Only one process may hold a given
  token: two pollers sharing one seed will invalidate each other and force a
  fresh browser login.

## Integrating

[`examples/home-assistant/`](examples/home-assistant/) has both wiring styles —
`command_line` sensors that poll in-container, and pushing states from an
external poller. [`examples/mcp-tools/`](examples/mcp-tools/) has tool schemas
for exposing the Xtra list to an LLM agent.

Agents working in this repo should read [SKILL.md](SKILL.md) first.

## Please be reasonable

These are personal-interoperability clients: read your own account, at human
frequency. Poll daily or hourly, not continuously. Do not resell the data, do
not run this against accounts that are not yours, and do not point it at a
provider that has asked you to stop.

## Licence

MIT.
