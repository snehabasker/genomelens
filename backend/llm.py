"""Provider-agnostic LLM calls with metering.

Every call emits an `llm_call` event carrying time-to-first-token, total latency, token
counts, cost and whether it was served from the response cache. Two providers:

  cloud   Anthropic Messages API (streaming, structured JSON output)
  local   Ollama on localhost - nothing leaves the machine, cost is zero

`run.provider == "local"` hard-disables the cloud path: the Anthropic client is never even
constructed, so the "no data sent to an LLM API" claim is structural, not a setting.
"""
from __future__ import annotations

import hashlib
import json
import time
import asyncio
from typing import Callable, Optional

import httpx

import cache
from config import JUDGE_MODEL, OLLAMA_MODEL, OLLAMA_URL, SYNTH_EFFORT, SYNTH_MODEL, cost_usd
from runtime import Run

_client = None
LOCAL_TIMEOUT_S = 70.0


class LLMError(Exception):
    """The model could not be used at all (billing, auth, network, outage). Never retried."""


class LLMBadOutput(LLMError):
    """The model answered, but not with usable output (refusal, truncation, invalid JSON). Retryable."""


def _anthropic():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(max_retries=2, timeout=90.0)
    return _client


def model_for(run: Run, role: str) -> str:
    if run.provider == "local":
        return OLLAMA_MODEL
    return JUDGE_MODEL if role == "judge" else SYNTH_MODEL


async def _cloud(model: str, system: str, user: str, schema: Optional[dict], effort: str,
                 max_tokens: int):
    kwargs = {"model": model, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}],
              "output_config": {"effort": effort}}
    if schema:
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    t0 = time.perf_counter()
    ttft = None
    try:
        async with _anthropic().messages.stream(**kwargs) as stream:
            async for _ in stream.text_stream:
                if ttft is None:
                    ttft = int((time.perf_counter() - t0) * 1000)
            msg = await stream.get_final_message()
    except Exception as e:  # SDK raises typed errors; the caller only needs "it failed, and why"
        raise LLMError(f"{type(e).__name__}: {str(e)[:200]}") from e
    if msg.stop_reason == "refusal":
        raise LLMBadOutput("model refused the request")
    if msg.stop_reason == "max_tokens":
        raise LLMBadOutput("output truncated at max_tokens")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return text, msg.usage.input_tokens, msg.usage.output_tokens, ttft or int((time.perf_counter() - t0) * 1000)


async def _local(system: str, user: str, schema: Optional[dict], max_tokens: int, attempt: int = 0):
    try:   # hard wall-clock cap: a 7B model can fall into a repetition loop and generate for minutes
        return await asyncio.wait_for(_local_stream(system, user, schema, max_tokens, attempt), LOCAL_TIMEOUT_S)
    except asyncio.TimeoutError as e:
        raise LLMError(f"local model gave no complete answer within {LOCAL_TIMEOUT_S:.0f}s") from e


async def _local_stream(system: str, user: str, schema: Optional[dict], max_tokens: int, attempt: int):
    payload = {"model": OLLAMA_MODEL, "stream": True, "keep_alive": "10m",
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               # temperature 0 is deterministic, so a retry must vary something or it repeats the failure
               "options": {"temperature": 0 if attempt == 0 else 0.5, "seed": attempt, "num_predict": max_tokens,
                           "num_ctx": 8192}}
    if schema:
        payload["format"] = schema
    t0 = time.perf_counter()
    ttft, parts, in_tok, out_tok = None, [], 0, 0
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=3.0)) as c:
            async with c.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
                if r.status_code != 200:
                    raise LLMError(f"Ollama HTTP {r.status_code}: {(await r.aread())[:160]!r}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    ev = json.loads(line)
                    piece = (ev.get("message") or {}).get("content", "")
                    if piece:
                        if ttft is None:
                            ttft = int((time.perf_counter() - t0) * 1000)
                        parts.append(piece)
                    if ev.get("done"):
                        in_tok, out_tok = ev.get("prompt_eval_count", 0), ev.get("eval_count", 0)
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama unreachable at {OLLAMA_URL} ({type(e).__name__}). "
                       f"Start it and `ollama pull {OLLAMA_MODEL}`.") from e
    return "".join(parts), in_tok, out_tok, ttft or int((time.perf_counter() - t0) * 1000)


async def generate(run: Run, role: str, system: str, user: str, schema: Optional[dict] = None,
                   max_tokens: int = 4000, effort: Optional[str] = None, attempt: int = 0,
                   validator: Optional[Callable] = None):
    """Returns (parsed_json_or_text, meta). Raises LLMError / LLMBadOutput.

    `validator(result)` must raise if the result is unusable. Only validated results are cached: caching
    first and validating later turns one bad generation into a permanent one (the retry would be served
    the same bad answer from the cache)."""
    if run.chaos.llm_down:
        await run.emit({"type": "llm_call", "data": {"role": role, "provider": run.provider,
                        "model": model_for(run, role), "error": "chaos: LLM provider unreachable",
                        "ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}})
        raise LLMError("LLM provider unreachable (injected fault)")
    if run.provider not in ("cloud", "local"):
        raise LLMError(f"provider '{run.provider}' has no LLM")

    model = model_for(run, role)
    effort = effort or ("low" if role == "judge" else SYNTH_EFFORT)
    key = hashlib.sha256(json.dumps([run.provider, model, effort, system, user, schema, attempt],
                                    sort_keys=True).encode()).hexdigest()
    t0 = time.perf_counter()

    hit = cache.llm_get(key) if run.features.resp_cache else None
    if hit and validator:
        try:
            validator(hit["response"])
        except Exception:
            hit = None            # an entry that no longer validates is a miss
    if hit:
        meta = {"role": role, "provider": run.provider, "model": model, "cached": True, "ttft_ms": 0,
                "ms": int((time.perf_counter() - t0) * 1000), "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "saved_usd": cost_usd(model, hit["input_tokens"], hit["output_tokens"])}
        await run.emit({"type": "llm_call", "data": meta})
        return hit["response"], meta

    if run.provider == "local":
        text, in_tok, out_tok, ttft = await _local(system, user, schema, max_tokens, attempt)
    else:
        text, in_tok, out_tok, ttft = await _cloud(model, system, user, schema, effort, max_tokens)

    meta = {"role": role, "provider": run.provider, "model": model, "cached": False, "ttft_ms": ttft,
            "ms": int((time.perf_counter() - t0) * 1000), "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": 0.0 if run.provider == "local" else cost_usd(model, in_tok, out_tok)}
    if schema:
        try:
            result = json.loads(text)
        except ValueError as e:
            meta["error"] = "invalid_json"
            await run.emit({"type": "llm_call", "data": meta})
            raise LLMBadOutput(f"model returned invalid JSON: {text[:120]!r}") from e
    else:
        result = text
    if validator:
        try:
            validator(result)
        except Exception as e:
            meta["error"] = "invalid_output"
            await run.emit({"type": "llm_call", "data": meta})
            raise LLMBadOutput(f"output failed validation: {str(e)[:140]}") from e
    await run.emit({"type": "llm_call", "data": meta})
    if run.features.resp_cache:
        cache.llm_put(key, result, in_tok, out_tok, model)
    return result, meta
