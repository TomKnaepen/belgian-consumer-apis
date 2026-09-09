# Exposing the shopping list to an LLM

`xtra-tools.json` is a set of OpenAI-style function definitions covering the
four Xtra operations, and `handlers.py` binds them to this library. Both are
examples: copy them into your own agent, do not import them.

```python
import json
from beapi import Xtra, from_env
from handlers import build_handlers

tools = json.load(open("xtra-tools.json"))
handlers = build_handlers(Xtra(api_key=from_env("XTRA_API_KEY"), ...))
result = await handlers[name](arguments)
```

## What the descriptions are doing

They read oddly for a reason, and the reasons transfer to any agent:

- **"translated to Dutch"** — the catalogue only matches Dutch product names.
  A model left to itself searches for "peanut butter" and gets nothing, then
  reports that Colruyt does not sell peanut butter.
- **"ask the user which one they mean"** — search returns plausible near-misses,
  and a wrong `product_id` puts the wrong photo in the app at the shelf.
- **"reactivates ... instead of adding a duplicate"** — the model needs to know
  this so it reports what actually happened.
- **"Call xtra_list_items first to get the id"** — ids are opaque uuids and
  never appear in conversation, so removal is always a two-step.

## Confirm before removing

`xtra_remove_item` is the only destructive call, and there is no undo — a
deleted line is gone, including its quantity. Gate it behind whatever
confirmation your agent framework offers rather than letting a model fire it
from an ambiguous "take that off the list".
