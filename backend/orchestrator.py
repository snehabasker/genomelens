"""Plan-and-Execute orchestrator (no agent framework).

    guardrails ─▶ session cache ─▶ VariantDecoder ─▶ ┌ ProteinImpact       ┐
                                                     ├ Pharmacogenomics    ├─▶ Synthesis ─▶ verified report
                                                     └ LiteratureClinical  ┘

Every stage streams typed events through `Run.emit`, which stamps them with a millisecond
offset (`t`). The UI renders purely from that event list, so a finished run can be replayed
and scrubbed exactly as it happened.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Awaitable, Callable, Optional

import cache
import guardrails
from agents.literature_clinical import LiteratureClinicalAgent
from agents.pharmacogenomics import PharmacogenomicsAgent
from agents.protein_impact import ProteinImpactAgent
from agents.synthesis import SynthesisAgent
from agents.variant_decoder import VariantDecoderAgent
from config import RUN_TIMEOUT_S, SESSION_CACHE_TTL_S
from runtime import Chaos, Features, Run, current_agent, current_run

Send = Callable[[dict], Awaitable[None]]


class Orchestrator:
    async def analyze(self, query: str, send: Send, *, provider: str = "cloud",
                      features: Optional[Features] = None, chaos: Optional[Chaos] = None,
                      preface: Optional[list] = None) -> dict:
        run = Run(query, provider, features, chaos, sink=send)
        run.preface = preface or []
        tok = current_run.set(run)
        try:
            await asyncio.wait_for(self._pipeline(run), timeout=RUN_TIMEOUT_S)
        except asyncio.TimeoutError:
            await run.emit({"type": "guard", "data": {
                "action": "timeout", "kind": "run_timeout", "snippet": "",
                "message": f"The analysis exceeded {RUN_TIMEOUT_S}s and was stopped. Partial results are shown."}})
            await self._complete(run, "timeout", {})
        finally:
            current_run.reset(tok)
        return {"status": run.events[-1]["data"].get("status"), "run": run}

    # ── pipeline ─────────────────────────────────────────────────────────────
    async def _pipeline(self, run: Run) -> None:
        f = run.features
        await run.emit({"type": "session_start", "data": {"query": run.query, "run_id": run.id,
                                                          "config": run.config()}})
        for note in getattr(run, "preface", []):
            await run.emit({"type": "guard", "data": note})

        # 1. input guardrails
        if f.guardrails:
            verdict = guardrails.check_input(run.query)
            if not verdict["ok"]:
                await run.emit({"type": "guard", "data": {
                    "action": "blocked", "kind": verdict["kind"], "message": verdict["message"],
                    "snippet": verdict["matched"] or verdict["normalized"][:120],
                    "suggestions": verdict["suggestions"]}})
                return await self._complete(run, "blocked", {})
            if verdict["rewritten"] and verdict["message"]:
                await run.emit({"type": "guard", "data": {
                    "action": "normalized", "kind": verdict["kind"], "message": verdict["message"],
                    "snippet": verdict["matched"] or ""}})
            query = verdict["normalized"]
        else:
            query = run.query.strip()

        # 2. session cache (only for clean, fault-free runs)
        ckey = hashlib.sha1(f"{run.provider}|{query}".encode()).hexdigest()
        if f.session_cache and not run.chaos.any():
            stored = cache.session_get(ckey, SESSION_CACHE_TTL_S)
            if stored:
                return await self._replay(run, stored)

        # 3. decode the variant
        vd = await self._decode(run, query)
        gene = vd.get("gene", "")
        if gene == "Raw Sequence":
            return await self._complete(run, "complete", vd)
        if not gene and f.early_exit:
            down = ", ".join(run.failed_sources)
            if down:
                msg = f"Could not look this up because {down} could not be reached. Try again shortly."
            elif vd.get("rs_id") and vd.get("position"):
                msg = f"{vd['rs_id']} resolves to chr{vd.get('chromosome')}:{vd['position']} but is not inside a known gene, so there is nothing to interpret."
            else:
                msg = f"“{query}” did not resolve to a human variant or gene."
            await run.emit({"type": "guard", "data": {
                "action": "fallback", "kind": "unresolved", "message": msg, "snippet": query[:80],
                "suggestions": guardrails.SUGGESTIONS}})
            return await self._complete(run, "fallback", vd)
        if not vd:
            vd = {"gene": "", "rs_id": "", "variant_type": "unknown", "cdna_change": query,
                  "chromosome": "", "position": None}

        # 4. parallel specialist agents
        decoder = VariantDecoderAgent()
        context = [self._run_context(run, decoder, vd)] if f.early_exit else []
        await asyncio.gather(
            *context,
            self._run_agent(run, ProteinImpactAgent(), variant_data=vd),
            self._run_agent(run, PharmacogenomicsAgent(), variant_data=vd),
            self._run_agent(run, LiteratureClinicalAgent(), variant_data=vd),
        )

        # 5. grounded synthesis + verification
        await self._run_agent(run, SynthesisAgent(), variant_data=vd)

        errored = any(e["type"] == "agent_error" for e in run.events)
        status = "partial" if (run.failed_sources or errored) else "complete"
        await self._complete(run, status, vd)
        if status == "complete" and f.session_cache and not run.chaos.any() and run.provider != "extractive":
            cache.session_put(ckey, run.events)

    async def _decode(self, run: Run, query: str) -> dict:
        vd: dict = {}

        async def capture(e: dict):
            nonlocal vd
            if e.get("type") == "variant_decoded":
                vd = e["data"]

        await self._run_agent(run, VariantDecoderAgent(), tap=capture, query=query)
        return vd

    async def _run_agent(self, run: Run, agent, tap=None, **kw) -> None:
        token = current_agent.set(agent.name)
        try:
            async for event in agent.run(**kw):
                await run.emit(event)
                if tap:
                    await tap(event)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # an agent failing must never take the session down
            await run.emit(agent.error(f"{type(e).__name__}: {e}"))
        finally:
            current_agent.reset(token)

    async def _run_context(self, run: Run, decoder, vd: dict) -> None:
        token = current_agent.set(decoder.name)
        try:
            async for event in decoder.fetch_context(vd):
                await run.emit(event)
        except Exception:
            pass
        finally:
            current_agent.reset(token)

    async def _replay(self, run: Run, stored: list) -> None:
        """Serve a finished analysis from the session cache: instant, free, still scrubbable."""
        saved = 0.0
        await run.emit({"type": "guard", "data": {
            "action": "cache_hit", "kind": "session_cache", "snippet": "",
            "message": "Served from the session cache - no database or model calls were made."}})
        prev_t = 0
        for ev in stored:
            if ev["type"] in ("session_start", "session_complete"):
                if ev["type"] == "session_complete":
                    saved = ev["data"].get("totals", {}).get("cost_usd", 0.0)
                continue
            await asyncio.sleep(min(0.05, max(0, ev["t"] - prev_t) / 1000 / 6))
            prev_t = ev["t"]
            await run.sink(ev)          # bypass run.emit: replayed calls must not count as spend
        final = next(e for e in stored if e["type"] == "session_complete")["data"]
        await run.emit({"type": "session_complete", "t": prev_t + 1, "data": {
            **final, "status": final["status"], "replayed": True, "saved_usd": saved,
            "totals": run.summary()}})

    async def _complete(self, run: Run, status: str, vd: dict) -> None:
        last = next((e for e in reversed(run.events) if e["type"] == "claims_verified"), None)
        await run.emit({"type": "session_complete", "data": {
            "status": status, "gene": vd.get("gene", ""), "variant": vd.get("cdna_change", run.query),
            "rs_id": vd.get("rs_id", ""), "totals": run.summary(),
            "grounding": last["data"]["stats"] if last else None,
            "degraded": dict(run.failed_sources)}})
