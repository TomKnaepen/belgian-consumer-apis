# Reverse-engineering notes

How each API was found, what it answers, and — as much as possible — the paths
that did not work. The dead ends are kept deliberately: they are what stops the
next person spending a week rediscovering that the portal is an SPA.

- [xtra.md](xtra.md) — Colruyt Xtra
- [monizze.md](monizze.md) — Monizze
- [pluxee.md](pluxee.md) — Pluxee

## On credentials in these documents

Two kinds of value show up here, and they are treated differently.

**Published:** OAuth/OIDC request parameters — client ids, redirect URIs,
scopes, locale hints. They are public by construction, they travel in plain
sight in redirect URLs, and knowing which client id belongs to which realm is
the single most useful finding in the Pluxee write-up.

**Not published:** gateway keys — Colruyt's `x-cg-apikey` and Pluxee's
`ocp-apim-subscription-key`. They are not personal secrets either, but they
meter quota, and shipping them working turns this repo into something you can
point at a provider without ever opening a browser. Each document says exactly
where to read them off your own session in thirty seconds.

Nothing here contains, or helps you reach, anybody's account but your own.
