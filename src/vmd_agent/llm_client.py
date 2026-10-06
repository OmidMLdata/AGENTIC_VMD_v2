"""A small client for the OpenAI-style chat API, using only the standard library.

Most model servers speak this API: **Ollama** (``http://localhost:11434/v1``),
llama.cpp's ``llama-server``, vLLM, LM Studio, and many hosted services. One client
therefore covers open-source models running on your own machine and hosted ones.

Only what the toolkit needs is implemented: chat completions with tool calling, and
listing the models a server has. Nothing here imports the rest of the package, so
it can be used by the chat command, the benchmark and any script alike.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Sequence

import numpy as np


class LLMError(RuntimeError):
    """The model server could not be reached or refused the request."""


# --------------------------------------------------------------- serialising
def json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def compact(obj, max_list: int = 24, max_str: int = 600):
    """Shrink a result for a model: long numeric lists become a summary and long
    strings are cut. The tool's real return value is not changed."""
    if isinstance(obj, dict):
        return {k: compact(v, max_list, max_str) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        if len(obj) > max_list:
            nums = [x for x in obj if isinstance(x, (int, float))
                    and not isinstance(x, bool)]
            if len(nums) == len(obj):
                a = np.asarray(nums, dtype=float)
                fin = a[np.isfinite(a)]
                return {"_list": len(obj), "first": list(obj[:3]),
                        "last": list(obj[-3:]),
                        "min": float(fin.min()) if len(fin) else None,
                        "max": float(fin.max()) if len(fin) else None}
            return [compact(x, max_list, max_str) for x in obj[:max_list]] + \
                   [f"... {len(obj) - max_list} more"]
        return [compact(x, max_list, max_str) for x in obj]
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + f"... [{len(obj) - max_str} more chars]"
    return obj


def render_result(obj, cap: int = 6000) -> str:
    text = json.dumps(compact(obj), default=json_default)
    return text if len(text) <= cap else text[:cap] + "...[truncated]"


# ------------------------------------------------------------------ requests
def _request(url: str, payload: Optional[dict], api_key: Optional[str],
             timeout: float) -> dict:
    data = None if payload is None else json.dumps(
        payload, default=json_default).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:600].decode("utf-8", "replace")
        raise LLMError(f"the model server answered HTTP {e.code} for {url}: "
                       f"{body}") from e
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise LLMError(f"cannot reach the model server at {url} ({reason}). "
                       "Is it running, and is the address right?") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        raise LLMError(f"the model server at {url} did not return JSON: "
                       f"{raw[:200]!r}") from e


def chat_completion(base_url: str, model: str, messages: Sequence[dict],
                    tools: Optional[Sequence[dict]] = None,
                    api_key: Optional[str] = None, temperature: float = 0.0,
                    max_tokens: Optional[int] = None,
                    timeout: float = 900.0,
                    tool_choice: Optional[str] = None) -> dict:
    """One non-streaming chat completion; returns the server's JSON. ``tool_choice="required"`` makes the
    model call a tool instead of answering from memory."""
    payload: Dict[str, object] = {"model": model, "messages": list(messages),
                                  "temperature": temperature, "stream": False}
    if tools:
        payload["tools"] = list(tools)
        if tool_choice:
            payload["tool_choice"] = tool_choice
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return _request(base_url.rstrip("/") + "/chat/completions", payload,
                    api_key, timeout)


def list_models(base_url: str, api_key: Optional[str] = None,
                timeout: float = 15.0) -> List[str]:
    """Ids of the models the server offers (``GET /models``)."""
    d = _request(base_url.rstrip("/") + "/models", None, api_key, timeout)
    items = d.get("data") if isinstance(d, dict) else None
    return [str(m.get("id")) for m in (items or []) if isinstance(m, dict)]


# --------------------------------------------------------------------- tools
def to_openai_tools(specs: Sequence[dict]) -> List[dict]:
    """Tool specs (``name``, ``description``, ``input_schema``) in the shape the
    chat API expects."""
    return [{"type": "function", "function": {
        "name": s["name"], "description": s.get("description", ""),
        "parameters": s.get("input_schema") or {"type": "object",
                                                "properties": {}}}}
        for s in specs]


def _loads_object(text) -> Optional[dict]:
    """Parse tool arguments that may arrive as a JSON string, a dict, or a string
    wrapped in a code fence; None if it cannot be read as an object."""
    if isinstance(text, dict):
        return text
    if text is None:
        return {}
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t:
        return {}
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    if m:
        t = m.group(1)
    try:
        v = json.loads(t)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _textual_calls(content: str, names: Sequence[str]) -> List[dict]:
    """Some open models write a tool call as JSON text instead of using the
    tool-call field. Accept ``{"name": ..., "arguments"|"parameters": {...}}``
    (or a list of them) **only** for a known tool name."""
    if not content or not names:
        return []
    t = content.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    if m:
        t = m.group(1).strip()
    if not t or t[0] not in "[{":
        return []
    try:
        v = json.loads(t)
    except ValueError:
        return []
    items = v if isinstance(v, list) else [v]
    out = []
    for it in items:
        if not isinstance(it, dict) or it.get("name") not in names:
            return []
        args = it.get("arguments", it.get("parameters", {}))
        parsed = _loads_object(args)
        out.append({"name": it["name"],
                    "arguments": parsed if parsed is not None else {},
                    "arguments_error": None if parsed is not None
                    else "arguments were not a JSON object"})
    return out


def parse_choice(response: dict, tool_names: Optional[Sequence[str]] = None
                 ) -> dict:
    """The first choice of a chat completion as
    ``{"content", "tool_calls", "finish_reason", "usage"}``.

    Each tool call is ``{"id", "name", "arguments", "arguments_error"}``.
    Arguments that are not valid JSON are reported in ``arguments_error`` rather
    than raising, so the model can be told and can retry."""
    try:
        choice = response["choices"][0]
        msg = choice.get("message") or {}
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise LLMError(f"unexpected reply from the model server: "
                       f"{str(response)[:300]}") from e
    content = msg.get("content")
    calls = []
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = (tc or {}).get("function") or {}
        args = _loads_object(fn.get("arguments"))
        calls.append({"id": tc.get("id") or f"call_{i}",
                      "name": fn.get("name") or "",
                      "arguments": args if args is not None else {},
                      "arguments_error": None if args is not None else
                      f"arguments were not a JSON object: "
                      f"{str(fn.get('arguments'))[:120]!r}"})
    if not calls and tool_names:
        for i, c in enumerate(_textual_calls(content or "", tool_names)):
            calls.append({"id": f"call_text_{i}", **c})
        if calls:
            content = None                     # it was a call, not an answer
    use = response.get("usage") or {}
    return {"content": content, "tool_calls": calls,
            "finish_reason": choice.get("finish_reason"),
            "usage": {"input_tokens": use.get("prompt_tokens") or 0,
                      "output_tokens": use.get("completion_tokens") or 0}}


def assistant_message(parsed: dict) -> dict:
    """The assistant turn to append to the history after :func:`parse_choice`."""
    msg: Dict[str, object] = {"role": "assistant",
                              "content": parsed.get("content") or ""}
    if parsed["tool_calls"]:
        msg["tool_calls"] = [{
            "id": c["id"], "type": "function",
            "function": {"name": c["name"],
                         "arguments": json.dumps(c["arguments"],
                                                 default=json_default)}}
            for c in parsed["tool_calls"]]
    return msg


def tool_message(call_id: str, name: str, text: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "name": name,
            "content": text}
