import json

import pytest

import cache
import grounding
import llm
from runtime import Chaos, Features, Run


def local_run(**kw):
    return Run("x", provider="local", features=Features(**kw))


def must_have_ok(d):
    if "ok" not in d:
        raise ValueError("missing ok")


async def test_invalid_output_is_never_cached(monkeypatch):
    """Regression: output was cached before validation, so the retry was served the same bad answer."""
    calls = []

    async def fake_local(system, user, schema, max_tokens, attempt=0):
        calls.append(attempt)
        return (json.dumps({"bad": 1}) if attempt == 0 else json.dumps({"ok": 1})), 10, 5, 3

    monkeypatch.setattr(llm, "_local", fake_local)
    run = local_run()
    schema = {"type": "object"}
    with pytest.raises(llm.LLMBadOutput):
        await llm.generate(run, "synthesis", "s", "regression-user-1", schema, validator=must_have_ok)
    out, meta = await llm.generate(run, "synthesis", "s", "regression-user-1", schema, attempt=1, validator=must_have_ok)
    assert out == {"ok": 1} and not meta["cached"] and calls == [0, 1]
    # and the good answer *is* cached
    out2, meta2 = await llm.generate(run, "synthesis", "s", "regression-user-1", schema, attempt=1, validator=must_have_ok)
    assert out2 == {"ok": 1} and meta2["cached"] and calls == [0, 1]


async def test_llm_down_chaos_raises_without_calling_a_model(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(llm, "_local", boom)
    run = local_run()
    run.chaos = Chaos(llm_down=True)
    with pytest.raises(llm.LLMError):
        await llm.generate(run, "synthesis", "s", "u", None)


async def test_local_provider_never_builds_the_cloud_client(monkeypatch):
    async def fake_local(*a, **k):
        return "hello", 1, 1, 1

    monkeypatch.setattr(llm, "_local", fake_local)
    monkeypatch.setattr(llm, "_anthropic", lambda: (_ for _ in ()).throw(AssertionError("cloud client built")))
    out, meta = await llm.generate(local_run(resp_cache=False), "synthesis", "s", "u", None)
    assert out == "hello" and meta["cost_usd"] == 0.0


async def test_judge_quote_must_be_in_the_evidence(monkeypatch):
    verdicts = iter([
        {"label": "supported", "quote": "ClinVar classifies rs334 as Pathogenic", "reason": "ok"},
        {"label": "supported", "quote": "this sentence appears nowhere in the evidence", "reason": "ok"},
    ])

    async def fake_generate(run, role, system, user, schema=None, **kw):
        return next(verdicts), {}

    monkeypatch.setattr(grounding.llm, "generate", fake_generate)
    ev = [{"id": "E1", "source": "ClinVar", "title": "t", "quarantined": False,
           "text": "ClinVar classifies rs334 as Pathogenic (review status: criteria provided)."}]
    claims = [{"text": "ClinVar classifies rs334 as Pathogenic.", "evidence_ids": ["E1"], "kind": "clinical"},
              {"text": "ClinVar classifies rs334 as Pathogenic too.", "evidence_ids": ["E1"], "kind": "clinical"}]
    run = Run("x", provider="local", features=Features())
    await grounding.verify(run, claims, ev)
    assert claims[0]["status"] == "supported"
    assert claims[1]["status"] == "partial" and "quote" in claims[1]["reason"]


def test_ledger_and_rate_limit():
    before = cache.spend_today()
    cache.spend_add(0.5)
    assert cache.spend_today() == pytest.approx(before + 0.5)
    ok = [cache.rate_check_and_log("test-ip-1", 3, 60)[0] for _ in range(4)]
    assert ok == [True, True, True, False]
