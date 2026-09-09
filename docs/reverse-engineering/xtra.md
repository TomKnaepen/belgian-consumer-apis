# Colruyt Xtra

## What it is

`www.colruyt.be` is served by a backend-for-frontend at `apix.colruyt.be`. The
BFF holds the real OAuth tokens server-side; the browser gets one opaque
session cookie. That is the whole of the client's authentication, which is why
this client has no refresh logic — there is nothing here to refresh.

| | |
|---|---|
| Shopping list BFF | `https://apix.colruyt.be/gateway/emec.colruyt.bffsvc/cg` |
| Product search | `https://apip.colruyt.be/gateway/emec.colruyt.protected.bffsvc/cg/nl/api/product-search-prs` |
| Auth | `clpbff_session` cookie + `x-cg-apikey` header |
| Cookie lifetime | roughly two months, no refresh, no warning |

## Credentials

1. Sign in at <https://www.colruyt.be>.
2. DevTools → Application → Cookies → `www.colruyt.be` → copy `clpbff_session`
   into `XTRA_SESSION_COOKIE`.
3. DevTools → Network → any request to `apix.colruyt.be` → copy the
   `x-cg-apikey` request header into `XTRA_API_KEY`.
4. From the same request's query string, copy `placeId` into `XTRA_PLACE_ID`.
   It identifies your store; search results and prices are relative to it.

`xtra login` verifies all three without changing anything.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/latest-shopping-list` | needs `placeId`, `lang`, `prs=true`, `limit`, `offset`, `sort` |
| POST | `/add-items-to-list` | body `{"items": [...]}`; **answers with the whole list** |
| DELETE | `/remove-item-from-list/{id}` | 204 |
| GET | product search | needs only the API key — no session |

## Things that will bite you

**The item array moves.** `add-items-to-list` answers `{"items": [...]}`.
`latest-shopping-list` answers `{"getListItems": {"data": [...]}, "getListModel":
{...}}` and has no `items` key at all. This client looks for both and then
recurses, and raises `ContractError` rather than returning `[]` when it finds
neither — reporting "your list is empty" because a field was renamed is the
worst available failure, since it sends someone to the shop without their list.

**`searchTerm` is load-bearing.** Other plausible parameter names
(`q`, `term`, `search`) are not rejected; they are silently ignored, and you get
the unfiltered catalogue back looking like a successful search.

**Timestamps are inconsistent.** `latest-shopping-list` returns `createdAt` as
epoch seconds; every other endpoint sends ISO strings. Normalised to ISO here.

**Adding an item that is already ticked off does nothing visible.** The endpoint
is idempotent per product and ignores `completedAt`: it bumps the quantity and
leaves the line ticked. No endpoint flips that flag. The only way to reactivate
is to delete the line and let the add recreate it, which is what `add_items`
does — but only for entries carrying a `product_id`, because a free-text line
cannot be matched to a product reliably.

**Ids are minted client-side.** The web client generates a uuid4 and the server
stores and echoes it rather than assigning its own.

**The list identity matters.** An account can hold several lists. The response
names the one it read, so a mismatch with the Xtra app is diagnosable instead of
looking like items vanishing.

## Product names

`name` is the bare product (`bananen`); `LongName` already includes brand and
content (`BONI bananen ±1kg`). They are kept separate in the normalised output
so callers do not compose `BONI BONI bananen ±1kg (±1kg)`.
