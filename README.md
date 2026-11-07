---
title: Genome Lens
emoji: 🧬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent variant analysis with cited, verified claims
---

# Genome Lens

**Multi-agent variant interpretation that shows its work, and shows where it breaks.**

Paste an rsID, a `GENE c.change`, a gene, or a DNA sequence. Four specialist agents query seven public databases in
parallel (dbSNP, NCBI Gene, Ensembl, UniProt, ClinVar, PubMed, ClinPGx/DGIdb), a synthesis step writes an interpretation
where **every claim cites its evidence**, and a verifier checks each claim against what it cited. Everything streams
live; every run can be replayed and scrubbed.

> Most agent demos show the happy path. This repo is built around the opposite: an [evaluation harness](#evaluation)
> with a **failure log**, a [post-mortem](docs/postmortem.md) of what actually broke, and a UI where you can attack the
> system and watch it hold (or not).

## What is in the app

| Tab | What it shows |
|---|---|
| **Lab** | Live agent graph, a waterfall of every database and model call (retries, cache hits and failures included), cited claims with a grounding bar, an evidence drawer, token / TTFT / cost counters, a privacy line stating exactly what left the machine, and a scrubber to replay any run. Inject faults (a source down, slow, returning garbage, a poisoned abstract, the AI provider offline). |
| **Try to break it** | Pick an attack; it runs twice at once, through the current pipeline and through the original v0 pipeline with every defence off, side by side. |
| **Evaluation** | The harness results: v0 vs v1 on every metric, latency/cost tables, and the failure log with a **Replay** button that opens the failing run in the Lab. |
| **Post-mortem** | The write-up of what broke and how it was found. |

## Run it

Requires Python 3.11+ and Node 18+.

```bash
cp .env.example .env              # optional: ANTHROPIC_API_KEY for the cloud model
cd backend && python -m venv venv && venv/Scripts/activate   # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cd ../frontend && npm install && npm run build && cp -r dist ../backend/static
cd ../backend && uvicorn main:app --port 8000                # http://localhost:8000
```

For development run `npm run dev` in `frontend/` (port 3000, proxies to the API on 8000).

**Local model (nothing sent to an LLM API).** Install [Ollama](https://ollama.com), `ollama pull qwen2.5:7b`, and pick
*Local* in the UI. It needs about 5 GB of VRAM or RAM. The cloud path uses `claude-opus-5-5` for synthesis and
`claude-haiku-5-5` as the verifier; both are configurable in `backend/config.py`.

**Without any model.** If neither is available (no key, no Ollama, or the daily budget is spent) the AI step is replaced by
a summary compiled straight from the database records, with a visible notice. The app never just fails.

```bash
cd backend && python -m pytest -q                 # 47 unit tests: guardrails, verifier, network layer, orchestrator
python eval/run_eval.py --config v1 --provider local   # the evaluation harness (see below)
python scripts/record_showcase.py --provider local     # regenerate the instant replays
```

## Architecture

```
 query ─▶ input guardrails ─▶ session cache ─▶ VariantDecoder ─▶ ┌ ProteinImpact       ┐
          (allow-list)        (replay)         (dbSNP/Gene)      ├ Pharmacogenomics    ├─▶ Synthesis ─▶ Verifier
                                                                 └ LiteratureClinical  ┘   (cited JSON)  (lexical + judge)
                 every database call goes through one instrumented network layer:
                 retries · response validation · TTL cache · NCBI throttle · fault injection · per-call events
```

* **No agent framework.** A plain asyncio orchestrator; every stage yields typed events stamped with a millisecond offset.
  The UI is a pure function of `(events, cursor)`, which is why replay and scrubbing cost nothing.
* **One network layer** (`backend/tools/net.py`) replaces `httpx` for all seven data tools. It is where retries, cache,
  rate limiting, validation and fault injection live, and where the waterfall's data comes from.
* **Grounding** (`backend/grounding.py`): a deterministic check (numbers, rsIDs and classification words must appear in
  the cited evidence; a classification must cite ClinVar) followed by a per-claim model judge that must quote its evidence.
* **Guardrails** (`backend/guardrails.py`): an *allow-list* front door (only recognised variant grammars pass) plus a scan
  of retrieved text for injected instructions, which are quarantined and never shown to the model.

## Evaluation

`backend/eval/dataset.jsonl` holds **71 test queries** in eight groups: known variants (20), HGVS (5), gene symbols (3),
common aliases (4), attacks (16, six of them held-out evasions written *after* the guardrails), malformed input (13),
poisoned retrieval (5) and infrastructure faults (5). Every run is scored on the real pipeline against the live
databases. The runner compares configurations (`v0` is the original code path, reproduced with feature flags), writes the
full event stream of every case, and the dashboard replays any failure.

Same code, same live databases, same model (`qwen2.5:7b` via Ollama); only the pipeline differs. `v0` is the original
behaviour, reproduced by switching the new defences off. Full table and per-case failure log: **Evaluation** tab.

| | v0 original | v1 | |
|---|---|---|---|
| Overall pass rate (71 cases) | 45% | **100%** | |
| Blocks prompt-injection / markup / advice bait (16, 6 held-out) | 0% | **100%** | allow-list vs. deny-list: 16/16 vs 1/6 on the held-out six |
| Stops safely on malformed input (13) | 8% | **100%** | v0 spent **220** wasted API calls on bad input; v1 spent 3 |
| Resolves aliases ("CYP2C19\*2", "MTHFR C677T") | 25% | **100%** | |
| Poisoned PubMed abstract reached the user (3 pathogenic cases) | **3/3** | **0/3** | blatant payloads quarantined; subtle ones only stopped by the verifier |
| Outages detected *and* disclosed (5) | 20% | **100%** | v0 reported a ClinPGx outage as "no interactions exist" |
| Claims with a number/class absent from all evidence | 7.5% | 10.8% (8.1% after the allele fix) | **not clearly improved** with a 7B model: now visible and attributable, not rarer |
| Latency p50, cold / warm cache | 31 s | 54 s / 34 s | v1 is slower; the verifier is not free |
| Model input tokens per run | 356 | 3,537 | ~10x |
| Projected cost per 1,000 requests (Opus 5.5 + Haiku 5.5 verifier) | $13.57 | $15.21 | +12% uncached; $3.80 at a 75% cache hit rate |

The **[post-mortem](docs/postmortem.md)** explains each failure and how it was found, including the ones I introduced
(a verifier change that silently collapsed the grounding metric, a response cache that could never hit, a real Ensembl
outage mid-project, and an allele the original code invented). The table above was measured before the allele fix; see section 9. It also lists what did *not* work.

## Learned variant prior (XGBoost + TensorFlow)

`backend/ml/` trains on 72,264 expert-curated missense variants from UniProt humsavar (LP/P vs LB/B, VUS dropped),
joined to the Swiss-Prot human sequences (all 72,264 reference residues verified against the sequence). Evaluation is
split **by gene**: the 14,604 test variants come from 2,539 genes the models never saw, so a model cannot score well by
memorising a gene's pathogenic rate.

| Tier | Model | AUROC | AUPRC |
|---|---|---|---|
| baseline | BLOSUM62 dissimilarity | 0.657 | 0.564 |
| substitution-only | XGBoost | 0.709 | 0.646 |
| substitution-only | Keras MLP (TensorFlow) | 0.711 | 0.650 |
| protein-context | XGBoost (+ window features) | 0.785 | 0.756 |
| protein-context | **TensorFlow 1D-CNN** over the ±15 residue window, fused with tabular features | 0.795 | 0.759 |
| protein-context | **XGBoost + CNN ensemble** | **0.804** | **0.776** |

Context features come from the wild-type sequence only: relative position, terminal distance, local hydropathy /
charge / volume windows, Gly-Pro and Cys density, window entropy, a transmembrane-helix proxy, protein composition.

```bash
pip install -r backend/requirements-ml.txt
cd backend && python -m ml.train        # ~4 min on CPU; downloads humsavar once, writes ml/artifacts/
python -c "from ml.predict import predict_missense as p; print(p('p.Phe508Ser', accession='P13569'))"
```

**Limits.** It is a prior, not a classifier you can act on: no multiple-sequence alignment, conservation or 3D
structure, and published tools using those score higher. Individual calls can be badly wrong; for example the
sickle-cell variant HBB p.Glu7Val scores only 0.20 while CFTR p.Phe508Ser scores 0.83. Labels are literature
curation, so they carry curation bias. It does not replace ClinVar or the grounded agents and is not wired into them.

## Deploying (Hugging Face Spaces, Docker SDK)

The repo root `Dockerfile` builds the frontend and serves everything from one container on port 7860. Create a Space with
the Docker SDK, push this repo, and set secrets as needed:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | enables the cloud model (optional; without it the AI step is the no-model summary) |
| `DAILY_BUDGET_USD` | hard daily cap on model spend (default 2.00). When reached, the AI step degrades gracefully |
| `RATE_LIMIT_RUNS`, `RATE_LIMIT_WINDOW_S` | per-IP limit (default 10 per 10 min). Replays are free and unlimited |

A Space has no GPU, so the public build relies on the recorded **instant replays** (real runs, real model, saved event
streams) plus the live attack lab and live database lookups.

## Honest limits

* **All results are from a local 7B model**, one run per configuration, so small differences are noise. The cloud code path
  (`claude-opus-5-5` + `claude-haiku-5-5`) is implemented but **was not exercised against the live API**: the account used for
  development had a zero credit balance. Cost figures are projections from measured token counts, not a bill.
* **Grounding is not a clinical safeguard.** The verifier makes unsupported claims visible; it does not make them rare, and a
  7B judge has false negatives. This is a research tool, not medical advice, and it refuses to give any.
* The subtle prompt-injection payload is not detected by any filter; it was stopped by a source rule (classifications must cite
  ClinVar) and by model behaviour, on a sample of three.
* I wrote the dataset and the defences; only the six held-out attacks are a fair test of the guardrails.
* Genomic sequence context for the helix needs Ensembl GRCh38, which was down for part of this project; `GENE c.X` inputs make
  no genomic-position claim at all.
* Public data sources change and rate-limit; two identical runs can differ.
