"""Per-analysis runtime context.

A `Run` is created for every analysis and published through context variables, so the
network layer (tools/net.py) and the LLM layer (llm.py) can emit instrumentation events
and honour feature flags / fault injection without every tool function threading a
parameter through.
"""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, fields
from typing import Awaitable, Callable, Optional

SOURCES = ["ClinVar", "PubMed", "dbSNP", "NCBI Gene", "Ensembl", "UniProt", "ClinPGx", "DGIdb"]


@dataclass
class Features:
    """Switchable defences/optimisations. `Features.baseline()` is the original pipeline."""
    guardrails: bool = True      # input validation, injection/advice detection, normalisation
    retry: bool = True           # retry+backoff, response validation on every data source
    http_cache: bool = True      # TTL cache for public-database responses
    resp_cache: bool = True      # cache for LLM responses
    session_cache: bool = True   # replay a finished analysis instead of recomputing
    grounding: bool = True       # structured, cited claims + verifier
    judge: bool = True           # LLM semantic verification on top of the lexical check
    quarantine: bool = True      # scan retrieved evidence for indirect prompt injection
    throttle: bool = True        # respect NCBI's request rate limit
    early_exit: bool = True      # stop when the variant can't be resolved; sequence context off the critical path
    retrieval: bool = True       # identifier-first PubMed queries
    honest_errors: bool = True   # report a down source as "unavailable", not as "no data found"

    @classmethod
    def baseline(cls) -> "Features":
        return cls(**{f.name: False for f in fields(cls)})

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Features":
        base = cls()
        for f in fields(cls):
            if d and f.name in d:
                setattr(base, f.name, bool(d[f.name]))
        return base


@dataclass
class Chaos:
    """Fault injection, used by the demo's Chaos panel and by the eval harness."""
    kill: list = field(default_factory=list)        # sources that refuse connections
    slow: list = field(default_factory=list)        # sources that add 3s latency
    malformed: list = field(default_factory=list)   # sources that return an HTML error page
    poison: str = ""                                # "blatant" | "subtle": malicious PubMed abstract
    llm_down: bool = False                          # the LLM provider is unreachable

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Chaos":
        d = d or {}
        pick = lambda k: [s for s in (d.get(k) or []) if s in SOURCES]  # noqa: E731
        return cls(kill=pick("kill"), slow=pick("slow"), malformed=pick("malformed"),
                   poison=d.get("poison") if d.get("poison") in ("blatant", "subtle") else "", llm_down=bool(d.get("llm_down")))

    def any(self) -> bool:
        return bool(self.kill or self.slow or self.malformed or self.poison or self.llm_down)


AGENT_PREFIX = {"variant_decoder": "D", "protein_impact": "P", "pharmacogenomics": "F", "literature_clinical": "L"}
EVIDENCE_ORDER = "DPFLE"


class Run:
    def __init__(self, query: str, provider: str = "cloud", features: Optional[Features] = None,
                 chaos: Optional[Chaos] = None,
                 sink: Optional[Callable[[dict], Awaitable[None]]] = None):
        self.id = uuid.uuid4().hex[:10]
        self.query = query
        self.provider = provider               # cloud | local | extractive
        self.features = features or Features()
        self.chaos = chaos or Chaos()
        self.sink = sink
        self.t0 = time.perf_counter()
        self.events: list[dict] = []
        self.evidence: list[dict] = []
        self.failed_sources: dict[str, str] = {}
        self.totals = {"tool_calls": 0, "cache_hits": 0, "retries": 0, "llm_calls": 0,
                       "llm_cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    def now(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    async def emit(self, event: dict) -> None:
        event.setdefault("t", self.now())
        event.setdefault("agent", current_agent.get() or None)
        t = event["type"]
        d = event.get("data") or {}
        if t == "tool_call":
            self.totals["tool_calls"] += 1
            self.totals["cache_hits"] += 1 if d.get("cached") else 0
            self.totals["retries"] += 1 if int(d.get("attempt", 1)) > 1 else 0
        elif t == "llm_call":
            self.totals["llm_calls"] += 1
            self.totals["llm_cache_hits"] += 1 if d.get("cached") else 0
            self.totals["input_tokens"] += d.get("input_tokens", 0)
            self.totals["output_tokens"] += d.get("output_tokens", 0)
            self.totals["cost_usd"] += d.get("cost_usd", 0.0)
        self.events.append(event)
        if self.sink:
            await self.sink(event)

    def fail_source(self, source: str, reason: str) -> None:
        self.failed_sources.setdefault(source, reason)

    def add_evidence(self, source: str, title: str, text: str, url: str = "") -> dict:
        from guardrails import scan_untrusted  # local import: guardrails has no runtime deps

        quarantined, reason = False, ""
        if self.features.quarantine:
            quarantined, reason = scan_untrusted(text)
        # IDs are per-agent (D1.. P1.. F1.. L1..) rather than global arrival order: parallel agents finish in
        # a different order every run, and an order-dependent ID changes the prompt and defeats the LLM cache.
        prefix = AGENT_PREFIX.get(current_agent.get() or "", "E")
        n = sum(1 for e in self.evidence if e["id"][0] == prefix) + 1
        item = {
            "id": f"{prefix}{n}",
            "source": source,
            "title": title,
            "text": "[quarantined: instruction-like content removed]" if quarantined else text,
            "url": url,
            "quarantined": quarantined,
            "reason": reason,
        }
        self.evidence.append(item)
        return item

    async def register(self, source: str, title: str, text: str, url: str = "") -> dict:
        """Add evidence and stream it (plus a guard event if it had to be quarantined)."""
        item = self.add_evidence(source, title, text, url)
        await self.emit({"type": "evidence", "data": dict(item)})
        if item["quarantined"]:
            await self.emit({"type": "guard", "data": {
                "action": "quarantined", "kind": "indirect_injection", "source": source,
                "message": f"Retrieved {source} text contained instruction-like content "
                           f"({item['reason']}). It was quarantined and never shown to the model.",
                "snippet": text[:160],
            }})
        return item

    def summary(self) -> dict:
        return {**self.totals, "cost_usd": round(self.totals["cost_usd"], 6), "ms": self.now(),
                "degraded_sources": dict(self.failed_sources)}

    def config(self) -> dict:
        return {"provider": self.provider, "features": asdict(self.features), "chaos": asdict(self.chaos)}


current_run: ContextVar[Optional[Run]] = ContextVar("current_run", default=None)
current_agent: ContextVar[Optional[str]] = ContextVar("current_agent", default=None)
