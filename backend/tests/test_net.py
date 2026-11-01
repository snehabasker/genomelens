import httpx as real
import pytest

from runtime import Chaos, Features, Run, current_run
from tools import net


def client(handler):
    return net.AsyncClient(transport=real.MockTransport(handler), timeout=5)


@pytest.fixture
def run():
    r = Run("x", features=Features(throttle=False))
    tok = current_run.set(r)
    yield r
    current_run.reset(tok)


async def test_retry_then_success(run):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return real.Response(503) if calls["n"] < 3 else real.Response(200, json={"ok": 1})

    async with client(handler) as c:
        r = await c.get("https://rest.uniprot.org/retry-test")
    assert r.json() == {"ok": 1} and calls["n"] == 3
    assert run.totals["retries"] == 2 and not run.failed_sources


async def test_gives_up_and_records_failure(run):
    async with client(lambda req: real.Response(500)) as c:
        r = await c.get("https://rest.uniprot.org/giveup-test")
    assert r.status_code == 500 and "UniProt" in run.failed_sources


async def test_kill_chaos(run):
    run.chaos = Chaos(kill=["ClinPGx"])
    async with client(lambda req: real.Response(200, json={})) as c:
        with pytest.raises(real.ConnectError):
            await c.get("https://api.clinpgx.org/v1/data/x")
    assert "ClinPGx" in run.failed_sources


async def test_malformed_json_is_detected(run):
    run.chaos = Chaos(malformed=["PubMed"])
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json"
    async with client(lambda req: real.Response(200, json={})) as c:
        with pytest.raises(real.DecodingError):
            await c.get(url)
    assert "PubMed" in run.failed_sources


async def test_http_cache(run):
    hits = {"n": 0}

    def handler(req):
        hits["n"] += 1
        return real.Response(200, json={"v": hits["n"]})

    async with client(handler) as c:
        a = await c.get("https://rest.uniprot.org/cache-test-1")
        b = await c.get("https://rest.uniprot.org/cache-test-1")
    assert a.json() == b.json() == {"v": 1} and hits["n"] == 1 and run.totals["cache_hits"] == 1


async def test_baseline_has_no_retry_or_cache():
    r = Run("x", features=Features.baseline())
    tok = current_run.set(r)
    try:
        n = {"c": 0}

        def handler(req):
            n["c"] += 1
            return real.Response(503)

        async with client(handler) as c:
            await c.get("https://rest.uniprot.org/baseline-test")
        assert n["c"] == 1 and r.totals["retries"] == 0
    finally:
        current_run.reset(tok)


async def test_plain_httpx_behaviour_outside_a_run():
    async with client(lambda req: real.Response(200, text="hi")) as c:
        assert (await c.get("https://example.com")).text == "hi"
