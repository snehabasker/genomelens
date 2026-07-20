import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from orchestrator import Orchestrator
from database import init_db, list_reports, get_report
from models import AnalysisRequest

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Genome Lens API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/reports")
async def get_reports():
    reports = await list_reports()
    return {"reports": reports}


@app.get("/api/reports/{report_id}")
async def get_single_report(report_id: int):
    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orchestrator = Orchestrator()

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)

            if message.get("type") == "analyze":
                query = message.get("query", "").strip()
                if not query:
                    await websocket.send_text(json.dumps({
                        "type": "session_error",
                        "data": {"error": "Empty query"}
                    }))
                    continue

                events_log = []

                async def send_event(text: str):
                    events_log.append(json.loads(text))
                    await websocket.send_text(text)

                await orchestrator.analyze(query, send_event)

                gene = next(
                    (e.get("data", {}).get("gene", "") for e in events_log
                     if e.get("type") == "variant_decoded"),
                    "",
                )
                try:
                    from database import save_report
                    await save_report(query, gene, events_log)
                except Exception:
                    pass

            elif message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "type": "session_error",
                "data": {"error": str(e)}
            }))
        except Exception:
            pass


# Serve built frontend in production
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built"}
