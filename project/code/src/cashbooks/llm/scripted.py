"""A deterministic stand-in LLM for tests and dry runs. No network.

It answers from a script keyed by the latest user message, and can be told to
call tools first, so the whole harness can be exercised end to end offline.
"""

from __future__ import annotations

import json
from typing import Callable

from cashbooks.llm.base import LLMResult, Message, ToolCall


class ScriptedLLM:
    model = "scripted"

    def __init__(self, replies: dict[str, dict] | None = None, tool_plan: dict[str, list[tuple[str, dict]]] | None = None,
                 default: dict | None = None):
        self.replies = replies or {}
        self.tool_plan = tool_plan or {}
        self.default = default or {"answerability": "ABSTAIN", "answer": "I can't tell from the records.",
                                   "as_of": "2026-09-24"}
        self.calls: list[tuple[str, list[Message]]] = []

    def _reply(self, messages: list[Message]) -> str:
        last = messages[-1].text if messages else ""
        for key, obj in self.replies.items():
            if key in last:
                return json.dumps(obj)
        return json.dumps(self.default)

    def complete(self, system: str, messages: list[Message], json_schema: dict | None = None) -> LLMResult:
        self.calls.append((system, messages))
        return LLMResult(text=self._reply(messages), input_tokens=len(system) // 4, output_tokens=50, model=self.model)

    def complete_with_tools(self, system: str, messages: list[Message], tools: list[dict],
                            call_tool: Callable[[str, dict], str], max_calls: int = 6) -> LLMResult:
        self.calls.append((system, messages))
        last = messages[-1].text if messages else ""
        trace = []
        for key, plan in self.tool_plan.items():
            if key in last:
                for name, args in plan[:max_calls]:
                    trace.append(ToolCall(name=name, args=args, result=call_tool(name, args)))
                break
        return LLMResult(text=self._reply(messages), tool_calls=trace, input_tokens=len(system) // 4,
                         output_tokens=50, model=self.model)
