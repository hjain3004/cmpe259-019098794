"""Provider-neutral interface every configuration talks to.

The harness never imports a provider SDK directly; it calls an `LLM`. That keeps
the four configurations identical apart from what goes into the context, and
lets tests run against a scripted stand-in with no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class Message:
    role: str  # "user" or "model"
    text: str


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    error: str | None = None


class LLM(Protocol):
    model: str

    def complete(self, system: str, messages: list[Message], json_schema: dict | None = None) -> LLMResult:
        """One generation. With json_schema, ask the provider for schema-constrained JSON."""

    def complete_with_tools(
        self,
        system: str,
        messages: list[Message],
        tools: list[dict],
        call_tool: Callable[[str, dict], str],
        max_calls: int = 6,
    ) -> LLMResult:
        """Run the tool-calling loop until the model answers in text or max_calls is reached."""


# ---------------------------------------------------------------- JSON Schema simplification


def simplify_schema(schema: dict) -> dict:
    """Pydantic JSON Schema -> a plain subset every provider accepts.

    Inlines $refs, turns Optional[X] (anyOf X|null) into X, keeps only type,
    description, properties, required, items, enum and format.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].split("/")[-1]]
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return walk(merged)
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            first = walk(options[0]) if options else {"type": "string"}
            if "description" in node and "description" not in first:
                first = {**first, "description": node["description"]}
            return first
        out: dict[str, Any] = {}
        for key in ("type", "description", "enum", "format"):
            if key in node:
                out[key] = node[key]
        if "const" in node:
            out["enum"] = [node["const"]]
            out.setdefault("type", "string")
        if "properties" in node:
            out["type"] = "object"
            out["properties"] = {k: walk(v) for k, v in node["properties"].items()}
            if node.get("required"):
                out["required"] = list(node["required"])
        if "items" in node:
            out["items"] = walk(node["items"])
        if out.get("format") not in (None, "date", "date-time"):
            out.pop("format")
        return out

    return walk(schema)


def extract_json(text: str) -> dict | None:
    """The first JSON object in a reply, tolerating code fences and leading prose."""
    if not text:
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None
