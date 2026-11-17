"""Gemini implementation of the LLM interface (google-genai SDK).

Configuration comes from the environment (or project/code/.env):
    GEMINI_API_KEY      required
    LLM_MODEL           pinned model ID, default below
    LLM_MIN_INTERVAL    seconds to wait between calls (free-tier rate limits), default 0

Temperature is 0 for every call. Automatic function calling is disabled: the
harness runs the tool loop itself so every call and result is logged.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from cashbooks.llm.base import LLMResult, Message, ToolCall

DEFAULT_MODEL = "gemini-3.6-flash"
MAX_RETRIES = 5


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from a .env file into os.environ (existing values win)."""
    path = path or Path(__file__).resolve().parents[3] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class GeminiLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        from google import genai  # imported here so tests never need the SDK

        load_env()
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY in project/code/.env")
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.min_interval = float(os.environ.get("LLM_MIN_INTERVAL", "0"))
        self._client = genai.Client(api_key=key)
        self._last = 0.0

    # ---------------------------------------------------------------- plumbing

    def _contents(self, messages: list[Message]):
        from google.genai import types

        return [types.Content(role=m.role, parts=[types.Part.from_text(text=m.text)]) for m in messages]

    def _call(self, contents, config):
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        delay = 4.0
        for attempt in range(MAX_RETRIES):
            try:
                self._last = time.monotonic()
                return self._client.models.generate_content(model=self.model, contents=contents, config=config)
            except Exception as e:  # rate limits and transient server errors
                msg = str(e)
                retryable = any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "500", "UNAVAILABLE", "DEADLINE"))
                if not retryable or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(delay)
                delay *= 2

    @staticmethod
    def _usage(resp) -> tuple[int, int]:
        u = getattr(resp, "usage_metadata", None)
        if not u:
            return 0, 0
        out = (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        return u.prompt_token_count or 0, out

    @staticmethod
    def _text(resp) -> str:
        try:
            parts = resp.candidates[0].content.parts or []
        except (AttributeError, IndexError, TypeError):
            return ""
        return "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))

    # ---------------------------------------------------------------- interface

    def complete(self, system: str, messages: list[Message], json_schema: dict | None = None) -> LLMResult:
        from google.genai import types

        cfg = dict(system_instruction=system, temperature=0)
        if json_schema is not None:
            cfg.update(response_mime_type="application/json", response_json_schema=json_schema)
        t0 = time.monotonic()
        try:
            resp = self._call(self._contents(messages), types.GenerateContentConfig(**cfg))
        except Exception as e:
            return LLMResult(text="", model=self.model, error=f"{type(e).__name__}: {e}",
                             latency_ms=int((time.monotonic() - t0) * 1000))
        i, o = self._usage(resp)
        return LLMResult(text=self._text(resp), input_tokens=i, output_tokens=o, model=self.model,
                         latency_ms=int((time.monotonic() - t0) * 1000))

    def complete_with_tools(self, system: str, messages: list[Message], tools: list[dict],
                            call_tool: Callable[[str, dict], str], max_calls: int = 6) -> LLMResult:
        from google.genai import types

        decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                           parameters_json_schema=t["input_schema"]) for t in tools]
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=0,
            tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = self._contents(messages)
        trace: list[ToolCall] = []
        tin = tout = 0
        t0 = time.monotonic()
        for _ in range(max_calls + 1):
            try:
                resp = self._call(contents, config)
            except Exception as e:
                return LLMResult(text="", model=self.model, error=f"{type(e).__name__}: {e}", tool_calls=trace,
                                 input_tokens=tin, output_tokens=tout, latency_ms=int((time.monotonic() - t0) * 1000))
            i, o = self._usage(resp)
            tin, tout = tin + i, tout + o
            content = resp.candidates[0].content if resp.candidates else None
            calls = [p.function_call for p in (content.parts or []) if getattr(p, "function_call", None)] if content else []
            if not calls:
                return LLMResult(text=self._text(resp), tool_calls=trace, input_tokens=tin, output_tokens=tout,
                                 model=self.model, latency_ms=int((time.monotonic() - t0) * 1000))
            if len(trace) + len(calls) > max_calls:
                break
            contents.append(content)  # keep the model turn intact (thought signatures included)
            parts = []
            for fc in calls:
                args = dict(fc.args or {})
                result = call_tool(fc.name, args)
                trace.append(ToolCall(name=fc.name, args=args, result=result))
                parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=parts))
        # Tool budget spent: ask for the final answer without tools.
        contents.append(types.Content(role="user", parts=[types.Part.from_text(
            text="Tool budget reached. Answer now from the tool results above, in the required JSON format.")]))
        final_cfg = types.GenerateContentConfig(system_instruction=system, temperature=0)
        try:
            resp = self._call(contents, final_cfg)
        except Exception as e:
            return LLMResult(text="", model=self.model, error=f"{type(e).__name__}: {e}", tool_calls=trace,
                             input_tokens=tin, output_tokens=tout, latency_ms=int((time.monotonic() - t0) * 1000))
        i, o = self._usage(resp)
        return LLMResult(text=self._text(resp), tool_calls=trace, input_tokens=tin + i, output_tokens=tout + o,
                         model=self.model, latency_ms=int((time.monotonic() - t0) * 1000))
