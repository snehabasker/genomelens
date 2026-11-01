"""Evaluation harness.

    python eval/run_eval.py --config v1 --provider local
    python eval/run_eval.py --config v0 --provider local --only k01,x01,c02

Each config gets its own cache database, wiped at start (`--keep-cache` to reuse), so cold-start
numbers are honest. Per-case results (with the full event stream, replayable in the UI) go to
eval/results/<config>/<id>.json and the aggregate to eval/results/<config>.json.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

ap = argparse.ArgumentParser()
ap.add_argument("--config", default="v1")
ap.add_argument("--provider", default="local", choices=["cloud", "local", "extractive"])
ap.add_argument("--only", default="")
ap.add_argument("--category", default="")
ap.add_argument("--concurrency", type=int, default=2)
ap.add_argument("--keep-cache", action="store_true")
ap.add_argument("--tag", default="")
args = ap.parse_args()

cache_dir = HERE / ".cache"
cache_dir.mkdir(exist_ok=True)
db = cache_dir / f"{args.config}.db"            # a tag (e.g. _warm) re-uses its config's cache
name = args.config + args.tag
if args.tag:
    args.keep_cache = True
if not args.keep_cache and db.exists():
    db.unlink()
os.environ["CACHE_DB"] = str(db)

from eval.metrics import aggregate, extract, judge  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from runtime import Chaos, Features  # noqa: E402

CONFIGS = {
    "v0": Features.baseline(),
    "v1": Features(session_cache=False),                      # everything on (session cache off: measure the pipeline)
    "v1-no-quarantine": Features(session_cache=False, quarantine=False),
    "v1-no-judge": Features(session_cache=False, judge=False),
    "v1-no-grounding": Features(session_cache=False, grounding=False),
}


async def run_case(case: dict, sem: asyncio.Semaphore) -> dict:
    events: list = []

    async def send(e):
        events.append(e)

    async with sem:
        t0 = time.perf_counter()
        try:
            await Orchestrator().analyze(case["query"], send, provider=args.provider,
                                         features=CONFIGS[args.config], chaos=Chaos.from_dict(case.get("chaos")))
            crashed = ""
        except Exception as e:  # a crash is a result, not a reason to stop the harness
            crashed = f"{type(e).__name__}: {e}"
        wall = int((time.perf_counter() - t0) * 1000)
    m = extract(events)
    if crashed:
        m["status"] = "crashed"
    v = judge(case, m)
    print(f"{'PASS' if v['passed'] else 'FAIL'} {case['id']:<4} {case['category']:<9} {wall/1000:5.1f}s "
          f"{m['status']:<9} gene={m['gene'] or '-':<8} claims={m['n_claims']:<2} "
          f"{'' if v['passed'] else [k for k, ok in v['checks'].items() if not ok]} {crashed}", flush=True)
    return {"case": case, "metrics": m, "verdict": v, "events": events, "crash": crashed, "wall_ms": wall}


async def main():
    cases = [json.loads(l) for l in (HERE / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    if args.category:
        cases = [c for c in cases if c["category"] in args.category.split(",")]
    print(f"config={name} provider={args.provider} cases={len(cases)}", flush=True)
    sem = asyncio.Semaphore(args.concurrency)
    rows = await asyncio.gather(*[run_case(c, sem) for c in cases])

    out = HERE / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        (out / f"{r['case']['id']}.json").write_text(json.dumps(r), encoding="utf-8")
    agg = aggregate(rows)
    agg.update(config=name, provider=args.provider, date=time.strftime("%Y-%m-%d"),
               failures=[{"id": r["case"]["id"], "category": r["case"]["category"], "query": r["case"]["query"][:80],
                          "failed": [k for k, ok in r["verdict"]["checks"].items() if not ok]}
                         for r in rows if not r["verdict"]["passed"]])
    (HERE / "results" / f"{name}.json").write_text(json.dumps(agg, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in agg.items() if k not in ("failures", "by_category")}, indent=1))


asyncio.run(main())
