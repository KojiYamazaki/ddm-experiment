"""Mock Commerce API for experiment simulation.

Provides search and purchase endpoints without real transactions.
All interactions are logged for post-hoc analysis.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.config import CATALOG_PATH


@dataclass
class APICall:
    """Record of a single API interaction."""
    timestamp: float
    endpoint: str
    request: dict
    response: dict
    latency_ms: float


@dataclass
class PurchaseResult:
    """Result of a purchase attempt."""
    success: bool
    order_id: Optional[str]
    items: list[dict]
    total_price: int
    message: str


class MockCommerceAPI:
    """Simulated commerce API with search and purchase capabilities."""

    def __init__(self):
        with open(CATALOG_PATH) as f:
            self.catalog = json.load(f)
        self.call_log: list[APICall] = []
        self._order_counter = 0

    def search_products(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        max_price: Optional[int] = None,
        min_rating: Optional[float] = None,
        in_stock_only: bool = True,
    ) -> list[dict]:
        """Search the product catalog with optional filters."""
        start = time.monotonic()
        results = list(self.catalog)

        if category:
            results = [p for p in results if p["category"] == category.lower()]
        if brand:
            results = [p for p in results if p["brand"].lower() == brand.lower()]
        if max_price is not None:
            results = [p for p in results if p["price"] <= max_price]
        if min_rating is not None:
            results = [p for p in results if p["rating"] >= min_rating]
        if in_stock_only:
            results = [p for p in results if p["in_stock"]]
        if query:
            q = query.lower()
            results = [
                p for p in results
                if q in p["name"].lower() or q in p["description"].lower()
            ]

        elapsed = (time.monotonic() - start) * 1000
        request = {
            "query": query, "category": category, "brand": brand,
            "max_price": max_price, "min_rating": min_rating,
            "in_stock_only": in_stock_only,
        }
        self.call_log.append(APICall(
            timestamp=time.time(), endpoint="search_products",
            request=request, response={"count": len(results), "products": results},
            latency_ms=elapsed,
        ))
        return results

    def get_product(self, product_id: str) -> Optional[dict]:
        """Get a single product by ID."""
        start = time.monotonic()
        result = None
        for p in self.catalog:
            if p["id"] == product_id:
                result = p
                break
        elapsed = (time.monotonic() - start) * 1000
        self.call_log.append(APICall(
            timestamp=time.time(), endpoint="get_product",
            request={"product_id": product_id},
            response=result if result else {"error": "not_found"},
            latency_ms=elapsed,
        ))
        return result

    def purchase(self, items: list[dict]) -> PurchaseResult:
        """Attempt to purchase items. items = [{"product_id": str, "quantity": int}, ...]

        This is a MOCK — no real transaction occurs.
        """
        start = time.monotonic()
        purchased = []
        total = 0

        for item in items:
            product = self.get_product(item["product_id"])
            if product is None:
                elapsed = (time.monotonic() - start) * 1000
                result = PurchaseResult(
                    success=False, order_id=None, items=[],
                    total_price=0,
                    message=f"Product {item['product_id']} not found",
                )
                self.call_log.append(APICall(
                    timestamp=time.time(), endpoint="purchase",
                    request={"items": items}, response=asdict(result),
                    latency_ms=elapsed,
                ))
                return result
            if not product["in_stock"]:
                elapsed = (time.monotonic() - start) * 1000
                result = PurchaseResult(
                    success=False, order_id=None, items=[],
                    total_price=0,
                    message=f"Product {item['product_id']} is out of stock",
                )
                self.call_log.append(APICall(
                    timestamp=time.time(), endpoint="purchase",
                    request={"items": items}, response=asdict(result),
                    latency_ms=elapsed,
                ))
                return result

            qty = item.get("quantity", 1)
            purchased.append({
                "product_id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "quantity": qty,
                "subtotal": product["price"] * qty,
            })
            total += product["price"] * qty

        self._order_counter += 1
        order_id = f"ORD-{self._order_counter:04d}"
        elapsed = (time.monotonic() - start) * 1000
        result = PurchaseResult(
            success=True, order_id=order_id, items=purchased,
            total_price=total,
            message=f"Order {order_id} placed successfully. Total: {total} USD",
        )
        self.call_log.append(APICall(
            timestamp=time.time(), endpoint="purchase",
            request={"items": items}, response=asdict(result),
            latency_ms=elapsed,
        ))
        return result

    def get_log(self) -> list[dict]:
        """Return all API calls as dicts for serialization."""
        return [asdict(c) for c in self.call_log]

    def reset_log(self):
        """Clear the API call log."""
        self.call_log.clear()


# Tool definitions for LLM function calling
TOOL_DEFINITIONS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog with optional filters. Returns a list of matching products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search query"},
                    "category": {"type": "string", "description": "Product category filter (e.g., 'camera', 'lens', 'accessory')"},
                    "brand": {"type": "string", "description": "Brand name filter (e.g., 'Sony', 'Canon')"},
                    "max_price": {"type": "integer", "description": "Maximum price in USD"},
                    "min_rating": {"type": "number", "description": "Minimum rating (0.0 to 5.0)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Get detailed information about a specific product by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "The product ID (e.g., 'CAM-001')"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "purchase",
            "description": "Purchase one or more products. Completes the transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "default": 1},
                            },
                            "required": ["product_id"],
                        },
                        "description": "List of items to purchase",
                    },
                },
                "required": ["items"],
            },
        },
    },
]

TOOL_DEFINITIONS_ANTHROPIC = [
    {
        "name": "search_products",
        "description": "Search the product catalog with optional filters. Returns a list of matching products.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query"},
                "category": {"type": "string", "description": "Product category filter (e.g., 'camera', 'lens', 'accessory')"},
                "brand": {"type": "string", "description": "Brand name filter (e.g., 'Sony', 'Canon')"},
                "max_price": {"type": "integer", "description": "Maximum price in USD"},
                "min_rating": {"type": "number", "description": "Minimum rating (0.0 to 5.0)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_product",
        "description": "Get detailed information about a specific product by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The product ID (e.g., 'CAM-001')"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "purchase",
        "description": "Purchase one or more products. Completes the transaction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "quantity": {"type": "integer", "default": 1},
                        },
                        "required": ["product_id"],
                    },
                    "description": "List of items to purchase",
                },
            },
            "required": ["items"],
        },
    },
]
