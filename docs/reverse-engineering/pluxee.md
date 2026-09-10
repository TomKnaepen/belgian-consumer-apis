# Pluxee

The long one. Pluxee has no consumer API, no scrapable HTML, and a portal that
actively resists the obvious approaches. This is the route that works and,
below it, the six that do not — each of which looked correct until a day had
gone into it.

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
| IdP | `https://connect.pluxee.app/op` (OIDC) |
| Token endpoint | `https://connect.pluxee.app/op/oidc/token` |
| Cards | `https://api.pluxee.app/gl/eva/bff/v2/be/cards` |
| Mobile client_id | `42d2b4b6-1a86-4b29-bd5e-2b8ce3814c31` |
| redirect_uri | `app.pluxee.consumers.eva://home/` |
| `ui_locales` | `en-BE` |
| scope | `openid profile email phone .../gl/payment/scopes/user-app` |
| resource | `https://api.pluxee.app/gl/payment/ https://api.pluxee.app/gl/psca/` |
| Subscription key | `ocp-apim-subscription-key` — a static string; read it off your own session |

### The client_id is realm-bound

This is the finding that cost the most and saves the most. An earlier attempt
used `265f74a6-77b4-47ee-9df3-2abb1a313708`, a client id recovered from the
same app snapshot, and the login page came back in French and rejected the
(Belgian) email as unknown. The realm is bound to the `client_id`: with the
wrong one you are not looking at a broken login, you are looking at the right
login for the wrong country. `ui_locales=en-BE` routes it the rest of the way.

If you are scanning the app yourself you will find `265f74a6` too. It is not
the one.

Note also that `offline_access` is **not** required in the request — the native
client is granted a refresh token regardless. Asking for it is harmless but
unnecessary.

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

A device-trust cookie, `op_device` / `op_device.sig`, is set on
`connect.pluxee.app` with about a year's lifetime. It authenticates nothing on
its own, but a browser that still holds it is treated as a known device, and a
later re-auth asks for a password rather than an emailed one-time code. Worth
doing the re-auth in the same browser profile.

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
so there is no lockout risk of the kind the legacy portal had.

### Reading the balance

```json
{"cards": [{"benefits": [
  {"externalProductType": "W1",
   "amount": {"value": 12345, "exponent": 2},
   "expiringBalances": [{"expiryDate": "2028-01-31T00:00:00Z"}]}]}]}
```

Amounts are minor units with an exponent — `12345 / 10²` = €123.45. The
`expiryDate` is the **money's** expiry, not the credential's, which makes it a
far more useful thing to show than a token countdown.

| Code | Pass |
|---|---|
| `W1` | Lunch |
| `W2` | Gift |
| `W4` | Eco |
| `W5` | Sport & Culture |

Key on `externalProductType`, never on the display name beside it — that one is
localised.

A pass type you do not hold raises `ContractError` rather than returning zero:
here, unlike Monizze, asking for a specific card and getting silence is a
question worth surfacing.

The BFF authorises on the plain `openid profile email` token plus the
subscription key. No balance-specific scope is involved — see below.

### invalid_grant arrives on a 400

A spent or revoked refresh token comes back as OAuth's `invalid_grant`, which
RFC 6749 carries on **400**, not the 401 that normally signals expiry. Code
that only maps 401/403 to "re-authenticate" will report the single most likely
Pluxee failure as a generic upstream error.

## What does not work

Kept in full, because every one of these is a plausible-looking road with a day
at the end of it. Two were written up as firm "do not build this" conclusions
before the mobile client turned up.

### There is no official API

Pluxee runs a developer portal at `apimdevportal.pluxee.app` on Azure API
Management. It is B2B — merchants, affiliates, corporate benefit administrators
— sign-up gated, with nothing resembling a cardholder balance or transaction
endpoint. Checking this first is reasonable; it is a dead end.

### The Drupal portal at `users.pluxee.be` is a legacy shell

It still serves a login form, it still identifies as Drupal 11, and posting
credentials to it still behaves like a login. It is simply no longer what
authenticates you, and no balance is rendered anywhere in it. Grepping that
page for `hcaptcha` or `oauth` returns nothing and tells you nothing, because
the real IdP is on a different host.

This is the trap that makes the existing prior art look usable. See below.

### Scraping the consumer portal

`consumers.pluxee.be` is client-side rendered — a root div and an ES module
bundle. The balance is never in the served markup; it arrives over XHR after
the app boots.

### Lifting a token from the browser

The SPA's `sessionStorage` (under
`oidc.user:https://connect.pluxee.app/op/:<client_id>`) holds an opaque access
token with a **30-minute** lifetime, an id token good for **five**, and **no
refresh token**. It lives in `sessionStorage`, so it dies with the tab.

A paste-a-token-when-it-expires flow — the approach that works fine for
Monizze, whose JWT lasts weeks — is therefore not viable. Nobody pastes a token
every half hour.

### The web SPA's client, with `offline_access`

The country web clients are configured in the SPA bundle at
`consumers.pluxee.be/assets/index-*.js`, keys `pluxeeConnectClientId` and
`pluxeeConnectRedirectUri`, as per-country JSON (`at`, `be`, `bg`, `de`, `lu`,
`ro`, `tn`). The Belgian one is `c6d7526f-b20b-40d4-bd4a-09e8701eb4a1`, with
`https://consumers.pluxee.be/oidc/callback` as its only registered redirect.

The discovery document at `/op/.well-known/openid-configuration` advertises
everything you would need: `refresh_token` in `grant_types_supported`,
`offline_access` in `scopes_supported`, `S256` PKCE, and `none` in
`token_endpoint_auth_methods_supported` (public client, no secret). The
authorize endpoint even *accepts* `offline_access` — it routes to login rather
than erroring.

The token response drops it every time:

| Request | Response |
|---|---|
| `scope=openid profile email offline_access` | `scope: "openid profile email"`, no refresh token |
| same, plus `prompt=consent` | identical, no refresh token |

The advertised capability is not grantable to this client. Two side notes worth
having: `prompt=consent` makes the custom login UI stall on the email step
(retrying clears it), because their interaction UI has no consent screen; and
the balance scope the discovery document advertises,
`.../gl/payment/spl/scopes/splprl-balance`, is rejected outright with
`invalid_scope — requested scope is not allowed`. You do not need it. The BFF
authorises on the plain token plus the subscription key.

### Silent renew against the IdP session

The obvious fallback — `prompt=none` against the provider's own session cookie,
which is how the SPA itself stays alive — is not available either. The OP
implements no session management: `check_session_iframe` is absent from the
discovery document, every issued token carries `session_state: null`, and
`op_session` does not persist in the browser. The SPA re-logs in rather than
renewing.

Tried against the mobile client with a live `op_session`, `prompt=none` returns
`login_required` ("End-User authentication is required").

The only cookies that do persist on `connect.pluxee.app` are `am_session_be`
(the account manager's own session, not the OP's) and the `op_device` pair
described above.

### Dynamic client registration

The discovery document advertises
`registration_endpoint: https://connect.pluxee.app/op/oidc/register`, which
would solve everything — register your own client asking for `offline_access`
with a `localhost` redirect, and no app archaeology is needed.

It is closed:

```
POST /op/oidc/register  {"redirect_uris":"not-an-array"}
→ 400 {"error":"invalid_request","error_description":"no access token provided"}
```

An initial access token is required and only Pluxee can issue one. Note the
status is misleading: the response carries `www-authenticate: Bearer`, and the
body is the real signal, not the 400.

## How this was found

The Android package is `com.pluxeegroup.consumers.global` (from
`consumers.pluxee.be/.well-known/assetlinks.json`; iOS is
`57CH23LE7E.com.pluxeegroup.consumers.global`). It is a Flutter app, so the
interesting strings live in the Dart snapshot at `lib/arm64-v8a/libapp.so`.

**Strings-only scanning gets you part way.** Pulling the APK with `adb` and
running `strings` over the snapshot yields client ids and redirect URIs — they
are plain strings, and none of it is secret, since a `client_id` rides in the
authorize URL in the clear. It also yields `res/raw/config.json`, which maps
`EVA_BEL → issuer: "sdx_be"` against a French default of `sdx_fr`.

**It does not get you the realm parameter.** No `acr_values`, `ui_locales`,
`issuer` or `realm` literal survives in the snapshot — the app sets it at
runtime. It is definitely not `acr_values`: the OP's `acr_values_supported` are
assurance levels (`X`, `A`, `F`, …), not IdP identifiers.

**Probing the login page for it does not work either.** The plan was to find
the parameter that flips the interaction page from French to Dutch by GET
alone, no login required. But the interaction page is itself an SPA — a
`lang="en"` bootstrap shell that renders its language client-side — so every
parameter produces identical markup. The selector's effect is not observable
without executing the page's JS.

**What worked was `adb logcat`.** The app launches its login in a Custom Tab,
and the intent that does so carries the complete authorize URL — every
parameter in the table at the top of this document. No proxy interception, no
CA certificate on the device, no Dart decompiler.

## Prior art

**[Tib612/pluxee-api](https://github.com/Tib612/pluxee-api)** (MIT,
Belgium-only) is the library you will find first, and it is the reason the
legacy-portal dead end is so easy to fall into: it scrapes `users.pluxee.be`
with CSS selectors against the logged-in HTML. That worked against the old
Drupal portal. The balance is no longer served in that HTML, so the approach
cannot work now, however healthy the project is. Its issue history is itself a
record of how often this surface moves — two of its most recent fixes are
upstream login-flow breakages.

Its `aia_chaser` dependency existed to work around Pluxee serving an incomplete
TLS certificate chain. That is obsolete: the chain verifies cleanly today and
ordinary TLS verification is enough. It was also the library's most troublesome
part, failing on Raspberry Pi and Windows.

**[netsoft-ruidias/ha-custom-component-sodexo](https://github.com/netsoft-ruidias/ha-custom-component-sodexo)**
targets Sodexo **Portugal** and does not work against Belgian Pluxee. Useful
only as a reference for what a config-flow Home Assistant integration looks
like.
