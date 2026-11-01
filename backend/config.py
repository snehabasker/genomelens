"""Central settings. Everything tunable for the public demo lives here, overridable via env."""
import os

from dotenv import load_dotenv

load_dotenv()

# ── Models ───────────────────────────────────────────────────────────────────
SYNTH_MODEL = os.getenv("SYNTH_MODEL", "claude-opus-5-5")
SYNTH_EFFORT = os.getenv("SYNTH_EFFORT", "low")          # low | medium | high
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-5-5")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# USD per million tokens (input, output). Cache-read tokens are not used: the prompts are
# far below the minimum cacheable prefix, so response caching is the cost lever here.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.00, 50.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


# ── Public-demo limits ───────────────────────────────────────────────────────
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "2.00"))
RATE_LIMIT_RUNS = int(os.getenv("RATE_LIMIT_RUNS", "10"))        # analyses per window per IP
RATE_LIMIT_WINDOW_S = int(os.getenv("RATE_LIMIT_WINDOW_S", "600"))
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))
RUN_TIMEOUT_S = int(os.getenv("RUN_TIMEOUT_S", "120"))           # hard wall-clock cap per run

# ── Caches ───────────────────────────────────────────────────────────────────
HTTP_CACHE_TTL_S = int(os.getenv("HTTP_CACHE_TTL_S", str(24 * 3600)))
SESSION_CACHE_TTL_S = int(os.getenv("SESSION_CACHE_TTL_S", str(24 * 3600)))
