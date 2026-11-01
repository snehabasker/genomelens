"""Re-score saved per-case results (events are stored) without re-running anything.

    python eval/reaggregate.py v0 v1 v1-warm
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.metrics import aggregate, extract, judge  # noqa: E402

RES = Path(__file__).parent / "results"
CASES = {json.loads(l)["id"]: json.loads(l) for l in (Path(__file__).parent / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
for cfg in sys.argv[1:]:
    rows = []
    for f in sorted((RES / cfg).glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        r["case"] = CASES[r["case"]["id"]]          # pick up dataset edits without re-running
        r["metrics"] = extract(r["events"])
        if r.get("crash"):
            r["metrics"]["status"] = "crashed"
        r["verdict"] = judge(r["case"], r["metrics"])
        f.write_text(json.dumps(r), encoding="utf-8")
        rows.append(r)
    old = json.loads((RES / f"{cfg}.json").read_text(encoding="utf-8"))
    agg = aggregate(rows)
    agg.update(config=cfg, provider=old.get("provider"), date=old.get("date", time.strftime("%Y-%m-%d")),
               failures=[{"id": r["case"]["id"], "category": r["case"]["category"], "query": r["case"]["query"][:80],
                          "failed": [k for k, ok in r["verdict"]["checks"].items() if not ok]}
                         for r in rows if not r["verdict"]["passed"]])
    (RES / f"{cfg}.json").write_text(json.dumps(agg, indent=1), encoding="utf-8")
    print(cfg, {k: agg[k] for k in ("pass_rate", "claims_per_run", "grounded_rate", "partial_rate", "unsupported_claim_rate",
                                   "deterministic_fail_rate", "llm_calls_per_run", "poison_influenced_rate", "poison_reached_user_rate")})
