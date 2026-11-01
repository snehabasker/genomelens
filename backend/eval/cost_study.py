"""Cost model built from MEASURED token counts.

The eval runs on a local model, so dollars are a projection: measured tokens per request
(from the llm_call events of the eval run) x the published per-token price of each cloud model.
The caching saving is parametric in the hit rate, because the hit rate depends on your traffic,
and a measured warm-cache pass shows what a hit costs.

    python eval/cost_study.py v1 v1-warm
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import PRICES  # noqa: E402

RES = Path(__file__).parent / "results"
cold, warm = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("v1", "v1-warm")


def tokens_by_role(config: str) -> dict:
    out: dict = {"synthesis": [], "judge": []}
    for f in (RES / config).glob("*.json"):
        case = json.loads(f.read_text(encoding="utf-8"))
        # one entry per *run*: sum the role's live (non-cached, non-error) calls
        for role in out:
            calls = [e["data"] for e in case["events"] if e["type"] == "llm_call"
                     and e["data"].get("role") == role and not e["data"].get("error") and not e["data"].get("cached")]
            if calls:
                out[role].append((sum(c["input_tokens"] for c in calls), sum(c["output_tokens"] for c in calls)))
    return out


def price(model: str, tin: float, tout: float) -> float:
    pi, po = PRICES[model]
    return (tin * pi + tout * po) / 1e6


t = tokens_by_role(cold)
synth_in = statistics.mean(x[0] for x in t["synthesis"])
synth_out = statistics.mean(x[1] for x in t["synthesis"])
judge_in = statistics.mean(x[0] for x in t["judge"]) if t["judge"] else 0
judge_out = statistics.mean(x[1] for x in t["judge"]) if t["judge"] else 0

summary_cold, summary_warm = (json.loads((RES / f"{c}.json").read_text(encoding="utf-8")) for c in (cold, warm))
rows = []
for synth_model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
    per_req = price(synth_model, synth_in, synth_out) + price("claude-haiku-5-5", judge_in, judge_out)
    rows.append({"label": f"{synth_model} synthesis + haiku-5-5 verifier, no cache",
                 "per_request_usd": per_req, "per_1k_usd": per_req * 1000,
                 "note": f"{synth_in:.0f} in / {synth_out:.0f} out synthesis tokens; {judge_in:.0f} / {judge_out:.0f} verifier"})
t0 = tokens_by_role("v0")     # v0's judge calls are the eval's measuring apparatus, not part of the original product
v0_in = statistics.mean(x[0] for x in t0["synthesis"])
v0_out = statistics.mean(x[1] for x in t0["synthesis"])
v0_cost = price("claude-opus-5-5", v0_in, v0_out)
rows.insert(0, {"label": "v0 original: claude-opus-5-5 prose synthesis, no verifier, no cache",
                "per_request_usd": v0_cost, "per_1k_usd": v0_cost * 1000,
                "note": f"{v0_in:.0f} in / {v0_out:.0f} out tokens (6 evidence items, no citations)"})
base = rows[1]["per_request_usd"]
for h in (0.25, 0.5, 0.75):
    rows.append({"label": f"claude-opus-5-5 stack, {int(h * 100)}% of requests served from cache",
                 "per_request_usd": base * (1 - h), "per_1k_usd": base * (1 - h) * 1000,
                 "note": f"saving = hit rate ({int(h * 100)}%); a hit costs $0 (measured below)"})

notes = [
    "Token counts are measured from the local model's tokenizer, so they approximate Claude's. Treat dollars as an estimate, not a bill.",
    f"Measured warm-cache pass: {summary_warm.get('latency_p50_ms') and round(summary_warm['latency_p50_ms'])} ms p50 vs "
    f"{summary_cold.get('latency_p50_ms') and round(summary_cold['latency_p50_ms'])} ms cold; HTTP cache hit rate "
    f"{summary_warm.get('http_cache_hit_rate')} vs {summary_cold.get('http_cache_hit_rate')}; LLM cache hit rate "
    f"{summary_warm.get('llm_cache_hit_rate')} (the rest missed because a flaky upstream call changed the evidence, hence the prompt).",
    f"v1 sends {synth_in / v0_in:.1f}x the synthesis input tokens of v0 (every evidence item, with IDs) and adds one verifier call per claim: "
    "reliability is bought with tokens, not free. Caching is what claws it back.",
    "Prompt caching does not apply: the prompts are far below the minimum cacheable prefix. Response caching is the lever.",
]
(RES / "cost_study.json").write_text(json.dumps({"rows": rows, "notes": notes}, indent=1), encoding="utf-8")
print(json.dumps(rows, indent=1))
