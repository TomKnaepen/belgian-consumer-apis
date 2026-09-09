# Home Assistant

Two ways to get these balances into HA. They differ in where the Python runs,
and that is the whole decision.

## A — `command_line` sensors (HA polls)

[`command_line.yaml`](command_line.yaml). HA runs the CLI on its own schedule
and parses the JSON. Self-contained: no other service has to be up.

The catch is dependency management. `command_line` runs inside the HA core
container, where anything you `pip install` is gone after the next update. This
works well on a Container or Core install you control, and is fragile on HA OS.

## B — an external poller pushes states

[`push_balances.py`](push_balances.py) plus
[`rest_command.yaml`](rest_command.yaml). Something outside HA — a cron job, a
systemd timer, an application you already run — fetches the balances and POSTs
them to `/api/states/<entity_id>`. HA needs no Python of yours at all.

Use this when you already have a service running, when you are on HA OS, or
when you want one poll shared by several consumers.

Two things to know:

- **Pushed states do not survive a restart.** HA drops them and the entity reads
  `unknown` until the next push. Push on a short interval (15 minutes is
  comfortable) from a stored value rather than polling the provider that often.
- **`homeassistant.update_entity` becomes a no-op.** There is no update
  coroutine behind a pushed state, so any automation calling it to force a fresh
  read before showing the number will silently show a stale one instead. Give
  the poller an HTTP trigger and call that with a `rest_command` — see
  `rest_command.yaml`.

## Polling frequency

Daily is enough for a meal-voucher balance, and it is the neighbourly choice.
Every rule below still holds at that rate:

- Monizze and Xtra credentials expire on their own schedule regardless of how
  often you poll; alert on the expiry, do not poll harder to find out.
- A Pluxee refresh token needs to be used inside its rolling ~14-day TTL. Daily
  keeps it alive with a large margin.
