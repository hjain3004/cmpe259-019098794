"""Answering and extraction model through the Anthropic Messages API.

Same interface as GeminiLLM, so the configurations, prompts and scoring are
unchanged. Configuration comes from the environment (or project/code/.env):

    ANTHROPIC_API_KEY   required (CLAUDE_API_KEY also accepted)
    LLM_MODEL           default claude-haiku-5-5
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable

from cashbooks.llm.base import LLMResult, Message, ToolCall
from cashbooks.llm.gemini import load_env

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_TOKENS = 4096
RECORD_TOOL = "record_extraction"


def to_messages(messages: list[Message]) -> list[dict]:
    """Our roles are user/model; the API wants user/assistant and non-empty text."""
    out = []
    for m in messages:
        role = "assistant" if m.role in ("model", "assistant") else "user"
        out.append({"role": role, "content": m.text if m.text.strip() else "(no reply)"})
    return out


class ClaudeLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        import anthropic  # imported here so tests never need the SDK

        load_env()
        key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not key:
            raise RuntimeError("Set ANTHROPIC_API_KEY in project/code/.env")
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        if not self.model.startswith("claude"):
            self.model = DEFAULT_MODEL  # LLM_MODEL may still name a Gemini model from an earlier setup
        self._anthropic = anthropic
        # The SDK retries 429/5xx itself and honors retry-after.
        self._client = anthropic.Anthropic(api_key=key, max_retries=6, timeout=180.0)

    # ---------------------------------------------------------------- plumbing

    def _system(self, system: str) -> list[dict]:
        # Cache the shared prefix (system prompt, plus tools when present): it repeats on every call.
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def _call(self, **kw):
        try:
            # The current Messages API takes no sampling parameters (no temperature), so runs are not
            # bit-for-bit repeatable; every reply is logged instead.
            return self._client.messages.create(model=self.model, max_tokens=MAX_TOKENS, **kw)
        except self._anthropic.APIStatusError as e:
            msg = str(e)
            if "credit balance" in msg.lower():
                raise SystemExit(f"Stopped: API credit balance is too low for {self.model}.")
            if e.status_code in (401, 403):
                raise SystemExit("Stopped: ANTHROPIC_API_KEY was rejected. Check project/code/.env.")
            if e.status_code == 404:
                raise SystemExit(f"Stopped: model {self.model!r} not found. Set LLM_MODEL in project/code/.env.")
            raise

    @staticmethod
    def _usage(resp) -> tuple[int, int]:
        u = resp.usage
        i = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) + \
            (getattr(u, "cache_read_input_tokens", 0) or 0)
        return i, u.output_tokens or 0

    @staticmethod
    def _text(resp) -> str:
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def _fail(self, e: Exception, t0: float, trace=None, tin=0, tout=0) -> LLMResult:
        return LLMResult(text="", model=self.model, error=f"{type(e).__name__}: {e}", tool_calls=trace or [],
                         input_tokens=tin, output_tokens=tout, latency_ms=int((time.monotonic() - t0) * 1000))

    # ---------------------------------------------------------------- interface

    def complete(self, system: str, messages: list[Message], json_schema: dict | None = None) -> LLMResult:
        """With json_schema, the reply is forced through one tool whose input is that schema."""
        t0 = time.monotonic()
        kw = dict(system=self._system(system), messages=to_messages(messages))
        if json_schema is not None:
            kw["tools"] = [{"name": RECORD_TOOL, "description": "Record the extracted fields.",
                            "input_schema": json_schema}]
            kw["tool_choice"] = {"type": "tool", "name": RECORD_TOOL}
        try:
            resp = self._call(**kw)
        except Exception as e:
            return self._fail(e, t0)
        i, o = self._usage(resp)
        if json_schema is not None:
            block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
            text = json.dumps(block.input) if block is not None else self._text(resp)
        else:
            text = self._text(resp)
        return LLMResult(text=text, input_tokens=i, output_tokens=o, model=self.model,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    def complete_with_tools(self, system: str, messages: list[Message], tools: list[dict],
                            call_tool: Callable[[str, dict], str], max_calls: int = 6) -> LLMResult:
        api_tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                     for t in tools]
        api_tools[-1] = {**api_tools[-1], "cache_control": {"type": "ephemeral"}}
        msgs = to_messages(messages)
        trace: list[ToolCall] = []
        tin = tout = 0
        t0 = time.monotonic()
        for _ in range(max_calls + 1):
            try:
                resp = self._call(system=self._system(system), messages=msgs, tools=api_tools)
            except Exception as e:
                return self._fail(e, t0, trace, tin, tout)
            i, o = self._usage(resp)
            tin, tout = tin + i, tout + o
            uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not uses:
                return LLMResult(text=self._text(resp), tool_calls=trace, input_tokens=tin, output_tokens=tout,
                                 model=self.model, latency_ms=int((time.monotonic() - t0) * 1000))
            if len(trace) + len(uses) > max_calls:
                break
            msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            results = []
            for u in uses:
                args = dict(u.input or {})
                result = call_tool(u.name, args)
                trace.append(ToolCall(name=u.name, args=args, result=result))
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": result})
            msgs.append({"role": "user", "content": results})
        # Tool budget spent: ask for the final answer without further tool use.
        msgs.append({"role": "user", "content":
                     "Tool budget reached. Answer now from the tool results above, in the required JSON format."})
        if msgs[-2]["role"] == "user":  # keep roles alternating
            msgs[-2:] = [{"role": "user", "content": msgs[-2]["content"] + [{"type": "text", "text": msgs[-1]["content"]}]}]
        try:
            resp = self._call(system=self._system(system), messages=msgs, tools=api_tools, tool_choice={"type": "none"})
        except Exception as e:
            return self._fail(e, t0, trace, tin, tout)
        i, o = self._usage(resp)
        return LLMResult(text=self._text(resp), tool_calls=trace, input_tokens=tin + i, output_tokens=tout + o,
                         model=self.model, latency_ms=int((time.monotonic() - t0) * 1000))
