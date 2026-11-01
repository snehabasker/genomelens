"""Instrumented drop-in for `httpx` used by every data-source tool.

The tools do `from tools import net as httpx` and keep calling `httpx.AsyncClient(...)`.
When an analysis is running (runtime.current_run is set) every request additionally gets:

  * a `tool_call` event (source, latency, status, cache hit, attempt) for the live timeline
  * fault injection from the demo's Chaos panel (kill / slow / malformed)
  * retry with backoff on transport errors, 429/5xx and non-JSON bodies from JSON endpoints
  * a TTL response cache
  * an NCBI-friendly request throttle (3 req/s without an API key)
  * failure bookkeeping, so a *down* source is reported as down rather than as "no data"

Outside an analysis it behaves exactly like httpx.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Optional

import httpx as _httpx

import cache
from config import HTTP_CACHE_TTL_S
from runtime import current_agent, current_run

_DB_LABEL = {"clinvar": "ClinVar", "pubmed": "PubMed", "snp": "dbSNP", "gene": "NCBI Gene",
             "nuccore": "NCBI Gene"}
_HOST_LABEL = {"rest.ensembl.org": "Ensembl", "grch37.rest.ensembl.org": "Ensembl", "rest.uniprot.org": "UniProt",
               "api.clinpgx.org": "ClinPGx", "dgidb.org": "DGIdb"}
MAX_ATTEMPTS = 3
READ_TIMEOUT_CAP = 8.0
TOTAL_DEADLINE = 9.0     # connect + read timeouts add up (8s + 8s); this caps the whole request
NCBI_MIN_INTERVAL = 0.4

_ncbi_lock: Optional[asyncio.Lock] = None
_ncbi_last = 0.0


def __getattr__(name):  # HTTPError, Response, ... resolve to the real httpx
    return getattr(_httpx, name)


def source_of(request: _httpx.Request) -> str:
    host = request.url.host
    if host in _HOST_LABEL:
        return _HOST_LABEL[host]
    if host.endswith("ncbi.nlm.nih.gov"):
        db = request.url.params.get("db", "")
        return _DB_LABEL.get(db, "NCBI Gene")
    return host


def _expects_json(request: _httpx.Request) -> bool:
    return (request.url.params.get("retmode") == "json"
            or "json" in request.headers.get("accept", "")
            or "graphql" in request.url.path)


def _cache_key(request: _httpx.Request) -> str:
    raw = f"{request.method} {request.url} ".encode() + (request.content or b"")
    return hashlib.sha1(raw).hexdigest()


async def _throttle_ncbi() -> None:
    global _ncbi_lock, _ncbi_last
    if _ncbi_lock is None:
        _ncbi_lock = asyncio.Lock()
    async with _ncbi_lock:
        wait = NCBI_MIN_INTERVAL - (time.monotonic() - _ncbi_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _ncbi_last = time.monotonic()


def _rebuild(request, status, content, ctype) -> _httpx.Response:
    return _httpx.Response(status, content=content, headers={"content-type": ctype or "text/plain"},
                           request=request)


class AsyncClient(_httpx.AsyncClient):
    async def send(self, request: _httpx.Request, **kw) -> _httpx.Response:
        run = current_run.get()
        if run is None:
            return await super().send(request, **kw)

        source = source_of(request)
        feats, chaos = run.features, run.chaos
        key = _cache_key(request)
        attempts = MAX_ATTEMPTS if (feats.retry and not request.extensions.get("no_retry")) else 1
        if feats.retry:  # bound worst-case latency: no single request may hang for the tools' 20-30s
            t = request.extensions.get("timeout") or {}
            request.extensions["timeout"] = {k: (min(v, READ_TIMEOUT_CAP) if v else v) for k, v in t.items()}
        last_err = ""

        for attempt in range(1, attempts + 1):
            t0 = time.perf_counter()
            status, cached, err, resp = 0, False, "", None
            try:
                if source in chaos.slow:
                    await asyncio.sleep(3.0)
                if source in chaos.kill:
                    raise _httpx.ConnectError(f"chaos: {source} is down", request=request)

                hit = None
                if feats.http_cache and source not in chaos.malformed:
                    hit = cache.http_get(key, HTTP_CACHE_TTL_S)
                if hit:
                    resp, cached = _rebuild(request, *hit), True
                else:
                    if feats.throttle and request.url.host.endswith("ncbi.nlm.nih.gov"):
                        await _throttle_ncbi()
                    if source in chaos.malformed:
                        resp = _rebuild(request, 200, b"<html><body>502 Bad Gateway</body></html>",
                                        "text/html")
                    else:
                        try:
                            resp = await asyncio.wait_for(super().send(request, **kw),
                                                          TOTAL_DEADLINE if feats.retry else None)
                        except asyncio.TimeoutError:
                            raise _httpx.ReadTimeout(f"no response within {TOTAL_DEADLINE:.0f}s", request=request)
                status = resp.status_code

                if feats.retry and status in (429, 500, 502, 503, 504):
                    raise _httpx.HTTPStatusError(f"HTTP {status}", request=request, response=resp)
                if feats.retry and status == 200 and _expects_json(request):
                    try:
                        json.loads(resp.content)
                    except ValueError:
                        raise _httpx.DecodingError("response was not JSON", request=request)

                if not cached and feats.http_cache and status == 200:
                    cache.http_put(key, status, resp.content, resp.headers.get("content-type", ""))
                await _report(run, source, request, status, t0, cached, attempt, "")
                return resp
            except (_httpx.RequestError, _httpx.HTTPStatusError) as e:
                err = last_err = f"{type(e).__name__}: {e}"[:140]
                await _report(run, source, request, status, t0, cached, attempt, err)
                timed_out = isinstance(e, _httpx.TimeoutException)
                if attempt < attempts and not (timed_out and attempt >= 2):
                    rate_limited = status == 429
                    await asyncio.sleep(1.2 * attempt if rate_limited else 0.3 * attempt)
                    continue
                if not (request.extensions.get("no_retry") or request.extensions.get("optional")):
                    run.fail_source(source, last_err)   # (callers with a fallback / cosmetic calls judge for themselves)
                if isinstance(e, _httpx.HTTPStatusError) and resp is not None:
                    return resp  # let the tool see the real error status, as before
                raise
        raise RuntimeError("unreachable")


async def _report(run, source, request, status, t0, cached, attempt, err) -> None:
    path = request.url.path.rsplit("/", 1)[-1] or request.url.path
    await run.emit({"type": "tool_call", "agent": current_agent.get(), "data": {
        "source": source, "method": request.method, "path": path[:48], "status": status,
        "ms": int((time.perf_counter() - t0) * 1000), "cached": cached, "attempt": attempt,
        "error": err or None,
    }})
