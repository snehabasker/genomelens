# Genome Lens — Multi-Agent DNA Intelligence Platform

Paste a DNA variant and watch 4 AI agents investigate it in parallel — resolving coordinates, predicting protein impact, scanning drug interactions, and synthesizing clinical literature — all streamed live into an animated DNA helix UI.

## Quick Start (Development)

### 1. Set up environment variables

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 2. Run the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## Production (Docker)

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
docker build -t genome-lens .
docker run -p 8000:8000 --env-file .env genome-lens
# Visit http://localhost:8000
```

---

## Example Queries

| Query | Type |
|-------|------|
| `rs1801133` | SNP rs ID (MTHFR C677T) |
| `rs334` | Sickle cell trait variant |
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
        ├─UniProt      ├─PharmGKB  ├─ClinVar
        └─Ensembl VEP  └─DGIdb     ├─PubMed
                                   └─Claude claude-opus-4-8 (synthesis)
```

## Agents

| Agent | APIs Used | Output |
|-------|-----------|--------|
| **Variant Decoder** | NCBI E-utilities, Ensembl | Coordinates, sequence, variant type |
| **Protein Impact** | UniProt, Ensembl VEP | Domain, SIFT, PolyPhen, consequence |
| **Pharmacogenomics** | PharmGKB, DGIdb | Drug-gene interactions |
| **Literature & Clinical** | ClinVar, PubMed + Claude AI | Clinical interpretation |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | For AI synthesis in Literature agent |
| `NCBI_API_KEY` | No | Higher NCBI rate limits (10 req/s vs 3/s) |
| `PORT` | No | Backend port (default 8000) |
