"""Response bodies trimmed from real traffic, with all account data replaced."""

import base64
import json
from datetime import UTC, datetime, timedelta


def jwt(days_out: int) -> str:
    """A Monizze-shaped bearer token whose exp claim is *days_out* away."""
    exp = int((datetime.now(UTC) + timedelta(days=days_out)).timestamp())
    claims = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"Bearer header.{claims}.signature"


COMPLETED_BANANA = {
    "id": "e0efedb7-759c-48ab-8af7-6dc2ed398c9d",
    "description": "BONI bananen",
    "completedAt": "2025-07-27T20:18:06Z",
    "createdAt": 1753647486,
    "productData": {"productId": "29013", "quantity": 1},
}

FRESH_BANANA = {
    "id": "11112222-3333-4444-5555-666677778888",
    "description": "BONI bananen",
    "completedAt": None,
    "createdAt": "2026-08-10T10:00:00Z",
    "productData": {"productId": "29013", "quantity": 1},
}

FRESH_MILK = {
    "id": "aaaa1111",
    "description": "melk",
    "completedAt": None,
    "createdAt": "2026-08-08T08:00:00Z",
    "productData": {"productId": "12345", "quantity": 1},
}


def list_response(items, name="My shopping list on clp website"):
    return {
        "getListItems": {"data": items, "pageInfo": {"total": len(items)}},
        "getListModel": {"id": "list-1", "name": name, "isShared": True},
    }


def add_response(items):
    """add-items-to-list echoes the entire list, not just what changed."""
    return {"items": items}


SEARCH_RESPONSE = {
    "products": [
        {
            "technicalArticleNumber": "29013",
            "name": "bananen",
            "LongName": "BONI bananen ±1kg",
            "brand": "BONI",
            "content": "±1kg",
            "price": {"basicPrice": 2.29},
            "inPromo": False,
            "isAvailable": True,
            "fullImage": "https://example.invalid/full.jpg",
            "thumbNail": "https://example.invalid/thumb.jpg",
        }
    ]
}

MONIZZE_BALANCES = {
    "data": {
        "emv": {"total": 125.99, "count": 20},
        "eco": {"total": 40.0, "count": 1},
    }
}

PLUXEE_CARDS = {
    "cards": [
        {
            "benefits": [
                {
                    "externalProductType": "W1",
                    "amount": {"value": 17000, "exponent": 2},
                    "expiringBalances": [{"expiryDate": "2027-03-31T00:00:00Z", "amount": 1000}],
                },
                {
                    "externalProductType": "W4",
                    "amount": {"value": 25050, "exponent": 2},
                    "expiringBalances": [],
                },
            ]
        }
    ]
}
