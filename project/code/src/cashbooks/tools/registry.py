"""Dispatch a model's tool call: validate arguments, run the tool, return JSON.

business_id is bound into the Store by application code before any call.
"""

from __future__ import annotations

import json
from typing import Callable

from pydantic import ValidationError

from cashbooks.contracts.tools import parse_tool_call
from cashbooks.store.db import Store
from cashbooks.tools.bills import get_bill_status, list_open_bills
from cashbooks.tools.errors import ToolError
from cashbooks.tools.more import (
    compare_vendor_payment_details, get_source_evidence, match_payments, sum_amount_due, summarize_purchases,
)

IMPLEMENTED: dict[str, Callable] = {
    "list_open_bills": list_open_bills,
    "get_bill_status": get_bill_status,
    "match_payments": match_payments,
    "sum_amount_due": sum_amount_due,
    "compare_vendor_payment_details": compare_vendor_payment_details,
    "summarize_purchases": summarize_purchases,
    "get_source_evidence": get_source_evidence,
}


def run_tool(store: Store, name: str, arguments: dict) -> str:
    """Return the tool result as a JSON string, or {"error": ...} on failure."""
    try:
        args = parse_tool_call(name, arguments)
    except KeyError:
        return json.dumps({"error": f"unknown tool {name!r}"})
    except ValidationError as e:
        return json.dumps({"error": f"invalid arguments: {e.errors()[0]['msg']}"})
    fn = IMPLEMENTED.get(name)
    if fn is None:
        return json.dumps({"error": f"tool {name!r} is not available yet"})
    try:
        return fn(store, args).model_dump_json()
    except ToolError as e:
        return json.dumps({"error": str(e)})
