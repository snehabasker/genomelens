"""Deny-list vs allow-list on the attack cases (no network, no model).

A deny-list only blocks inputs that match a known-bad pattern. The shipped front door is an allow-list:
only recognised variant grammars get through. This prints how many of the attack cases each catches.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guardrails as g  # noqa: E402

cases = [json.loads(l) for l in (Path(__file__).parent / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
attacks = [c for c in cases if c["category"] == "attack"]


def denylist(q: str) -> bool:
    t = g.normalize(q)
    return bool(g._INJECTION_RE.search(t) or g._MARKUP_RE.search(t) or g._ADVICE_RE.search(t))


rows = []
for c in attacks:
    rows.append((c["id"], c.get("heldout", False), denylist(c["query"]), not g.check_input(c["query"])["ok"], c["query"][:60]))

for tag, sel in (("original 10", [r for r in rows if not r[1]]), ("held-out 6", [r for r in rows if r[1]])):
    print(f"{tag:12} deny-list only: {sum(r[2] for r in sel)}/{len(sel)}   allow-list (shipped): {sum(r[3] for r in sel)}/{len(sel)}")
print()
for r in rows:
    if not r[2]:
        print(f"  deny-list missed {r[0]}: {r[4]!r}  -> shipped front door: {'blocked' if r[3] else 'PASSED'}")
