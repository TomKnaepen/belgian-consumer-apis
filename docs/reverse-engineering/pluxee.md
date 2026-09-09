# Pluxee

The long one. Pluxee has no consumer API, no scrapable HTML, and a portal that
actively resists the two obvious approaches. This is the route that works and,
below it, the four that do not.

## What works

The **mobile app** authenticates against `connect.pluxee.app` with a native
OIDC client that is granted a refresh token. That is the whole trick: the web
SPA is a dead end, the app is not.

```
one-time browser login (auth code + PKCE, human solves the captcha)
        ↓
   refresh_token          ← rotates on every use, ~14-day rolling TTL
        ↓
   access_token           ← 30 minutes
        ↓
GET /gl/eva/bff/v2/be/cards
```

| | |
|---|---|
| IdP | `https://connect.pluxee.app/op` (OIDC, ES256) |
| Token endpoint | `https://connect.pluxee.app/op/oidc/token` |
| Cards | `https://api.pluxee.app/gl/eva/bff/v2/be/cards` |
| Mobile client_id | `42d2b4b6-1a86-4b29-bd5e-2b8ce3814c31` |
| redirect_uri | `app.pluxee.consumers.eva://home/` |
| `ui_locales` | `en-BE` |
| scope | `openid profile email phone .../gl/payment/scopes/user-app` |
| Subscription key | `ocp-apim-subscription-key` — read it off your own session |

### The client_id is realm-bound

This is the finding that cost the most and saves the most. An earlier attempt
used a different Pluxee client id found by proximity, and the login page came
back in French and rejected the (Belgian) email as unknown. The realm is bound
to the `client_id`: with the wrong one you are not looking at a broken login,
you are looking at the right login for the wrong country. `ui_locales=en-BE`
routes it the rest of the way.

Note also that `offline_access` is **not** required in the request — the native
client is granted a refresh token regardless.

### Obtaining the refresh token, once

1. Build an authorization-code + PKCE authorize URL with the client id,
   redirect uri, scope and `ui_locales` above, and open it in a browser.
2. Sign in. The captcha is solved by a human here, exactly once.
3. The redirect goes to a custom scheme, so the browser will refuse to follow
   it — read the `code` out of the address bar or the error page.
4. Exchange the code at the token endpoint with your PKCE verifier. Keep the
   `refresh_token` from the response.
5. Seed it into a token file: `{"alice": "<refresh_token>"}`, mode 600.

`beapi.TokenStore` reads and rewrites that file for you.

### Rotation — the one operational rule

**The refresh token rotates on every exchange, and the previous value dies
immediately.** Two consequences, both of which have bitten this code:

- Exactly **one** process may hold a given token. Seeding two pollers from the
  same value means whichever runs second authenticates with a revoked token,
  and recovery is the full browser login. This also rules out live CI tests
  against a production token.
- The replacement must be persisted **before** the balance request, not after.
  An exchange whose rotation was never stored has already burned the stored
  value. `Pluxee.access_token` does the write first, deliberately.

Recovery from a broken chain is one browser login. No password is ever stored,
so there is no lockout risk.

### Reading the balance

```json
{"cards": [{"benefits": [
  {"externalProductType": "W1",
   "amount": {"value": 17000, "exponent": 2},
   "expiringBalances": [{"expiryDate": "2027-08-30T00:00:00Z"}]}]}]}
```

Amounts are integers with an exponent — `17000 / 10²` = €170.00. The
`expiryDate` is the **money's** expiry, not the credential's.

| Code | Pass |
|---|---|
| `W1` | Lunch |
| `W2` | Gift |
| `W4` | Eco |
| `W5` | Sport & Culture |

A pass type you do not hold raises `ContractError` rather than returning zero:
here, unlike Monizze, asking for a specific card and getting silence is a
question worth surfacing.

### invalid_grant arrives on a 400

A spent or revoked refresh token comes back as OAuth's `invalid_grant`, which
RFC 6749 carries on **400**, not the 401 that normally signals expiry. Code
that only maps 401/403 to "re-authenticate" will report the single most likely
Pluxee failure as a generic upstream error.

## What does not work

Kept because each of these looks plausible until you have spent a day on it.

**The Drupal portal at `users.pluxee.be`.** A legacy shell. No balance is
rendered in it, and its login form is not the login.

**Scraping the consumer portal.** `consumers.pluxee.be` is client-side rendered.
The balance is never in the HTML — it arrives over XHR after the app boots.

**Lifting a token from the browser.** The SPA's `sessionStorage` holds an opaque
access token with a **30-minute** lifetime, an id token good for five, and **no
refresh token**; it survives by silent renew against the IdP session, and dies
with the tab. A paste-a-token-when-it-expires flow like the Monizze one is
therefore not viable — nobody pastes a token every half hour.

**Dynamic client registration.** Closed. The discovery document advertises the
capability; the endpoint refuses.

**The web SPA's own client id.** It is a public client, and it can complete a
PKCE flow — but it is not granted a refresh token, which puts you straight back
into the 30-minute problem.

## Where this came from

Captured with `adb logcat`, reading the intent that launches the app's login
Custom Tab. No proxy interception, no decompilation — the authorize URL is
right there in the intent, and it carries every parameter above.
