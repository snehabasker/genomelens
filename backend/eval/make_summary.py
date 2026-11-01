"""Combine eval/results/<config>.json files into the single summary.json the dashboard reads.

    python eval/make_summary.py v0 v1 [--model "qwen2.5:7b (local)"]
"""
import json
import sys
import time
from pathlib import Path

RES = Path(__file__).parent / "results"
LABELS = {"v0": "v0 · original", "v1": "v1 · current", "v1-warm": "v1 · warm cache",
          "v1-no-quarantine": "v1 − quarantine", "v1-no-judge": "v1 − judge", "v1-no-grounding": "v1 − grounding"}

args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = "an unspecified model"
if "--model" in sys.argv:
    model = sys.argv[sys.argv.index("--model") + 1]
    args = [a for a in args if a != model]

configs = {c: json.loads((RES / f"{c}.json").read_text(encoding="utf-8")) for c in args}
first = next(iter(configs.values()))
cost = RES / "cost_study.json"
summary = {
    "generated": time.strftime("%Y-%m-%d"),
    "provider": first.get("provider"), "model": model,
    "dataset": {"n": first["n"]},
    "order": list(configs), "labels": {c: LABELS.get(c, c) for c in configs},
    "configs": configs,
    "cost_study": json.loads(cost.read_text(encoding="utf-8")) if cost.exists() else None,
}
(RES / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("wrote", RES / "summary.json", "for", list(configs))
