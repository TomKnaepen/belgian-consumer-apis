# Monizze

## What it is

`my.monizze.be` is a single-page app talking to a JSON API at
`happy.monizze.be`. Authentication is a bearer JWT held in the browser. There
is no refresh flow reachable from outside the app, so the token is captured by
hand — but its `exp` claim sits about two months out, which makes a manual
capture perfectly workable.

| | |
|---|---|
| Balances | `GET https://happy.monizze.be/api/services/my-monizze/voucher/balances` |
| Auth | `Authorization: Bearer <jwt>` |
| Token lifetime | ~2 months, from the `exp` claim |

## Credentials

1. Sign in at <https://my.monizze.be>.
2. DevTools → Network → any request to `happy.monizze.be` → copy the
   `Authorization` header value into `MONIZZE_TOKEN`.

The `Bearer ` prefix is optional; the client adds it when it is missing.

For more than one account, put them in a token file instead:

```json
{ "alice": "eyJhbGci…", "bob": "eyJhbGci…" }
```

and set `MONIZZE_TOKEN_FILE` plus `MONIZZE_USER`.

## Response shape

```json
{ "data": { "emv": { "total": 125.99, "count": 20 },
            "eco": { "total": 40.00, "count": 1 } } }
```

| Key | Voucher |
|---|---|
| `emv` | meal |
| `eco` | eco |
| `gift` | gift |
| `cons` | consumption |

A voucher type you do not hold is simply absent, which the client reads as
`0.0` rather than an error — not holding an eco card is not a failure.

## Things that will bite you

**`Origin` and `Referer` are checked.** The request needs
`Origin: https://my.monizze.be`; without it the gateway refuses.

**Decode the expiry, do not wait for the 401.** The token dies quietly, and the
first symptom is otherwise a balance that reads "unavailable" at the till.
`monizze token` prints the days remaining; wire an alert at a week or so.

**A token that will not decode is not an expired token.** `token_expiry`
returns `("unknown", -1)` for anything it cannot parse, and a caller must not
treat that as an expiry — it usually means the value was pasted wrong.
