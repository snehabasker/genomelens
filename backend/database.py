import aiosqlite
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "reports.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                gene TEXT,
                created_at REAL NOT NULL,
                events TEXT NOT NULL
            )
        """)
        await db.commit()


async def save_report(query: str, gene: str, events: list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reports (query, gene, created_at, events) VALUES (?, ?, ?, ?)",
            (query, gene, time.time(), json.dumps(events)),
        )
        await db.commit()


async def list_reports(limit: int = 20) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, query, gene, created_at FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_report(report_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = await cursor.fetchone()
    if not row:
        return {}
    data = dict(row)
    data["events"] = json.loads(data["events"])
    return data
