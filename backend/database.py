import json
import os
import time
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.getenv("RUNS_DB", str(Path(__file__).parent / "runs.db")))


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                gene TEXT,
                status TEXT,
                provider TEXT,
                cost_usd REAL,
                ms INTEGER,
                created_at REAL NOT NULL,
                events TEXT NOT NULL
            )
        """)
        await db.commit()


async def save_run(run_id: str, query: str, events: list):
    done = next((e for e in reversed(events) if e.get("type") == "session_complete"), {"data": {}})["data"]
    start = next((e for e in events if e.get("type") == "session_start"), {"data": {}})["data"]
    totals = done.get("totals", {})
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, query, done.get("gene", ""), done.get("status", ""),
             start.get("config", {}).get("provider", ""), totals.get("cost_usd", 0.0),
             totals.get("ms", 0), time.time(), json.dumps(events)),
        )
        await db.commit()


async def list_runs(limit: int = 30) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, query, gene, status, provider, cost_usd, ms, created_at FROM runs "
            "ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def get_run(run_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = await cur.fetchone()
    if not row:
        return {}
    data = dict(row)
    data["events"] = json.loads(data["events"])
    return data
