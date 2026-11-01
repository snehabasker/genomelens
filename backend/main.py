import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import auth
import cache
import config
from database import get_run, init_db, list_runs, save_run
from orchestrator import Orchestrator
from presets import ATTACKS, CHAOS, EXAMPLES
from runtime import SOURCES, Chaos, Features

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
SHOWCASE_DIR = ROOT / "showcase"
EVAL_DIR = ROOT / "eval" / "results"

_slots = asyncio.Semaphore(config.MAX_CONCURRENT_RUNS)
_ollama = {"ts": 0.0, "up": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Genome Lens API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def ollama_up() -> bool:
    if time.time() - _ollama["ts"] > 15:
        try:
            async with httpx.AsyncClient(timeout=0.8) as c:
                names = [m["name"] for m in (await c.get(f"{config.OLLAMA_URL}/api/tags")).json().get("models", [])]
            _ollama["up"] = any(n.split(":")[0] == config.OLLAMA_MODEL.split(":")[0] for n in names)
        except Exception:
            _ollama["up"] = False
        _ollama["ts"] = time.time()
    return _ollama["up"]


def has_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def client_ip(ws: WebSocket) -> str:
    fwd = ws.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (ws.client.host if ws.client else "unknown")


# ── REST ─────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/config")
async def get_config():
    spent = cache.spend_today()
    return {
        "models": {"synthesis": config.SYNTH_MODEL, "judge": config.JUDGE_MODEL, "local": config.OLLAMA_MODEL},
        "cloud_available": has_key(), "local_available": await ollama_up(),
        "budget": {"daily_usd": config.DAILY_BUDGET_USD, "spent_usd": round(spent, 4),
                   "exhausted": spent >= config.DAILY_BUDGET_USD},
        "rate_limit": {"runs": config.RATE_LIMIT_RUNS, "window_s": config.RATE_LIMIT_WINDOW_S},
        "auth_required": auth.enabled(),
        "sources": SOURCES, "examples": EXAMPLES, "attacks": ATTACKS, "chaos": CHAOS,
    }


@app.get("/api/runs", dependencies=[Depends(auth.require_user)])
async def runs():
    return {"runs": await list_runs()}


@app.get("/api/runs/{run_id}", dependencies=[Depends(auth.require_user)])
async def one_run(run_id: str):
    run = await get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


def _json_file(path: Path):
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/showcase")
async def showcase_index():
    return _json_file(SHOWCASE_DIR / "index.json") if (SHOWCASE_DIR / "index.json").exists() else {"items": []}


@app.get("/api/showcase/{item_id}")
async def showcase_item(item_id: str):
    if not item_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "bad id")
    return _json_file(SHOWCASE_DIR / f"{item_id}.json")


@app.get("/api/eval")
async def eval_summary():
    return _json_file(EVAL_DIR / "summary.json")


@app.get("/api/eval/case/{config_name}/{case_id}")
async def eval_case(config_name: str, case_id: str):
    for part in (config_name, case_id):
        if not part.replace("_", "").replace("-", "").isalnum():
            raise HTTPException(400, "bad id")
    return _json_file(EVAL_DIR / config_name / f"{case_id}.json")


# ── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    try:
        auth.ws_user(ws)
    except ValueError:
        return await ws.close(code=4401, reason="unauthorized")
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("expected a JSON object")
            except ValueError as e:     # one bad frame must not kill the connection
                await ws.send_text(json.dumps({"type": "session_error",
                                               "data": {"error": f"Malformed message: {e}", "kind": "bad_frame"}}))
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "analyze":
                await handle_analyze(ws, msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # malformed frame etc. - report, don't crash the server
        try:
            await ws.send_text(json.dumps({"type": "session_error", "data": {"error": str(e)[:200]}}))
        except Exception:
            pass


async def handle_analyze(ws: WebSocket, msg: dict):
    query = msg.get("query")
    query = query if isinstance(query, str) else ""
    wanted = msg.get("provider") if msg.get("provider") in ("cloud", "local") else "cloud"
    features = Features() if msg.get("defenses", True) else Features.baseline()
    chaos = Chaos.from_dict(msg.get("chaos"))

    async def reject(kind: str, text: str):
        await ws.send_text(json.dumps({"type": "session_error", "data": {"error": text, "kind": kind}}))

    allowed, retry = cache.rate_check_and_log(client_ip(ws), config.RATE_LIMIT_RUNS, config.RATE_LIMIT_WINDOW_S)
    if not allowed:
        return await reject("rate_limit", f"Rate limit: {config.RATE_LIMIT_RUNS} analyses per "
                                          f"{config.RATE_LIMIT_WINDOW_S // 60} min. Try again in {retry}s - or replay a "
                                          "showcase run, which is free and unlimited.")
    if _slots.locked():
        return await reject("busy", "The server is at capacity. Try again in a few seconds.")

    preface, provider = [], wanted
    if wanted == "cloud":
        if not has_key():
            provider = "extractive"
            preface.append({"action": "fallback", "kind": "no_api_key", "snippet": "",
                            "message": "No Anthropic API key is configured on this server, so the AI step is replaced "
                                       "by a summary compiled directly from the databases."})
        elif cache.spend_today() >= config.DAILY_BUDGET_USD:
            provider = "extractive"
            preface.append({"action": "fallback", "kind": "budget", "snippet": "",
                            "message": f"The demo's daily AI budget (${config.DAILY_BUDGET_USD:.2f}) is used up. "
                                       "Database lookups still run live; the AI step is replaced by a direct "
                                       "compilation of the records. Cached answers are unaffected."})
    elif not await ollama_up():
        preface.append({"action": "warn", "kind": "local_unavailable", "snippet": "",
                        "message": f"Ollama with {config.OLLAMA_MODEL} was not detected on this server. The local "
                                   "model step will fall back to a no-model summary."})

    events: list = []

    async def send(event: dict):
        events.append(event)
        await ws.send_text(json.dumps(event))

    async with _slots:
        result = await Orchestrator().analyze(query, send, provider=provider, features=features,
                                              chaos=chaos, preface=preface)
    run = result["run"]
    cache.spend_add(run.totals["cost_usd"])
    try:
        await save_run(run.id, query[:200], events)
    except Exception:
        pass


# ── Frontend ─────────────────────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        index = STATIC_DIR / "index.html"
        return FileResponse(str(index)) if index.exists() else {"error": "Frontend not built"}
