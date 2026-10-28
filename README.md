# Genome Lens — Multi-Agent DNA Intelligence Platform

Paste a DNA variant and watch 4 AI agents investigate it — resolving coordinates, predicting protein impact, scanning drug interactions, and synthesizing clinical literature — all streamed live over a WebSocket into an animated DNA helix UI.

**Stack:** FastAPI + WebSockets (Python) · React 18 + TypeScript (strict) + Vite · custom plan-and-execute agent orchestrator (no agent framework) · Claude for clinical synthesis.

## Quick Start (Development)

Requires Python 3.11+ and Node 18+.

### 1. Set up environment variables

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 2. Run the backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000 (proxies /api and /ws to the backend on :8000)
```

Frontend scripts:

| Command | What it does |
|---------|--------------|
| `npm run dev` | Vite dev server with HMR |
| `npm run typecheck` | `tsc --noEmit` (strict mode) |
| `npm run build` | Typecheck, then production bundle into `dist/` |

---

## Production (Docker)

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
docker build -t genome-lens .
docker run -p 8000:8000 --env-file .env genome-lens
# Visit http://localhost:8000
```

The image builds the frontend and serves it from FastAPI, so one container serves both the UI and the API.

---

## Example Queries

| Query | Type |
|-------|------|
| `rs1801133` | SNP rs ID (MTHFR C677T) |
| `rs334` | Sickle cell variant (HBB p.Glu7Val) |
| `BRCA1 c.5266dupC` | HGVS cDNA notation |
| `MTHFR c.677C>T` | Gene + cDNA change |
| `TP53 c.817C>T` | Tumor suppressor variant |
| `ATGGATTTATCTGCTCTT...` | Raw DNA sequence |

---

## Architecture

```
WebSocket /ws ──► Orchestrator
                    │
               Phase 1 (sequential)
                    │
              VariantDecoderAgent
              ├── NCBI E-utilities  (rs ID → gene + coordinates)
              ├── Ensembl REST      (sequence context)
              └── sequence_tools    (HGVS parsing, translation)
                    │
               Phase 2 (parallel)
              ┌─────┼──────────────┐
              │     │              │
        ProteinImpact  Pharmaco   LiteratureClinical
        ├─UniProt      ├─ClinPGx   ├─ClinVar
        └─Ensembl VEP  └─DGIdb     ├─PubMed
                                   └─Claude (synthesis)
```

## Agents

| Agent | APIs Used | Output |
|-------|-----------|--------|
| **Variant Decoder** | NCBI E-utilities, Ensembl | Coordinates, sequence, variant type |
| **Protein Impact** | UniProt, Ensembl VEP | Domain, SIFT, PolyPhen, consequence |
| **Pharmacogenomics** | ClinPGx (formerly PharmGKB), DGIdb (GraphQL) | Drug-gene interactions |
| **Literature & Clinical** | ClinVar, PubMed + Claude AI | Clinical interpretation |

Each agent is an async generator that yields events; the orchestrator merges the three Phase 2 agents into one stream. A failure in one data source degrades that agent's section rather than the whole analysis.

## WebSocket protocol

The client sends `{"type": "analyze", "query": "<variant>"}` and receives a stream of JSON events:

| Event | Payload highlights |
|-------|--------------------|
| `session_start` / `session_complete` / `session_error` | query, gene/variant, error |
| `agent_start` / `agent_progress` / `agent_done` / `agent_error` | `agent`, message / error |
| `sequence_loaded`, `helix_highlight` | sequence window, mutation position / ref / alt |
| `variant_decoded` | gene, chromosome, position, variant type, cDNA change, rs ID |
| `protein_impact`, `drug_interactions`, `literature_found` | per-agent structured results |
| `report_section` | title, markdown content, confidence, sources |

The same contract is encoded as a discriminated union in [`frontend/src/types.ts`](frontend/src/types.ts), so every event handler in the UI is type-checked against what the backend emits.

## Project structure

```
backend/
  main.py            FastAPI app, /ws endpoint, REST /api/reports, static serving
  orchestrator.py    Plan-and-execute orchestration (decoder → 3 parallel agents)
  agents/            variant_decoder, protein_impact, pharmacogenomics, literature_clinical
  tools/             NCBI, Ensembl, UniProt, ClinPGx/DGIdb, ClinVar, PubMed clients
  database.py        SQLite (aiosqlite) report history
frontend/src/
  types.ts           WebSocket event + UI state types
  useWebSocket.ts    Typed socket hook with auto-reconnect
  App.tsx            State reducer for the event stream, 3-panel layout
  DNAHelix.tsx       Animated SVG helix  ·  AgentNodes / LiveStream / ReportBuilder
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | For AI synthesis in the Literature agent (the account needs available credits) |
| `NCBI_API_KEY` | No | Higher NCBI rate limits (10 req/s vs 3/s). Currently used by the variant-lookup client |

The backend port is set with the `uvicorn --port` flag (or the Docker `-p` mapping), not an env var.

## Troubleshooting

- **"AI synthesis unavailable"** in the Clinical Interpretation section — the Claude call failed. Check that `ANTHROPIC_API_KEY` is set and that the account has credit; the error text is shown in the report.
- **Some sections empty after a run** — the public APIs (NCBI in particular) rate-limit unauthenticated traffic and the Phase 2 agents query in parallel. Set `NCBI_API_KEY` and retry.
- **UI shows "disconnected"** — make sure the backend is running on port 8000 (the Vite dev server proxies `/ws` and `/api` there).

## Disclaimer

For research and education only. Output is not medical advice and is not a substitute for clinical-grade variant interpretation.
