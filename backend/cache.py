"""Small SQLite-backed stores: HTTP cache, LLM response cache, session cache, spend ledger,
rate-limit log. Synchronous on purpose - every operation is a single indexed row."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("CACHE_DB", str(Path(__file__).parent / "cache.db")))
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (key TEXT PRIMARY KEY, status INTEGER, content BLOB,
    content_type TEXT, created REAL);
CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, response TEXT, input_tokens INTEGER,
    output_tokens INTEGER, model TEXT, created REAL);
CREATE TABLE IF NOT EXISTS session_cache (key TEXT PRIMARY KEY, events TEXT, created REAL);
CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, cost REAL, ts REAL);
CREATE TABLE IF NOT EXISTS rate_log (ip TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS rate_ip ON rate_log (ip, ts);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
    return _conn


def _q(sql: str, args: tuple = ()):
    with _lock:
        return _db().execute(sql, args).fetchall()


# ── HTTP cache ───────────────────────────────────────────────────────────────
def http_get(key: str, ttl: float) -> Optional[tuple]:
    rows = _q("SELECT status, content, content_type, created FROM http_cache WHERE key=?", (key,))
    if rows and time.time() - rows[0][3] < ttl:
        return rows[0][0], rows[0][1], rows[0][2]
    return None


def http_put(key: str, status: int, content: bytes, content_type: str) -> None:
    _q("INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?,?)",
       (key, status, content, content_type, time.time()))


# ── LLM response cache ───────────────────────────────────────────────────────
def llm_get(key: str) -> Optional[dict]:
    rows = _q("SELECT response, input_tokens, output_tokens, model FROM llm_cache WHERE key=?", (key,))
    if rows:
        return {"response": json.loads(rows[0][0]), "input_tokens": rows[0][1],
                "output_tokens": rows[0][2], "model": rows[0][3]}
    return None


def llm_put(key: str, response: dict, input_tokens: int, output_tokens: int, model: str) -> None:
    _q("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?,?)",
       (key, json.dumps(response), input_tokens, output_tokens, model, time.time()))


# ── Session cache ────────────────────────────────────────────────────────────
def session_get(key: str, ttl: float) -> Optional[list]:
    rows = _q("SELECT events, created FROM session_cache WHERE key=?", (key,))
    if rows and time.time() - rows[0][1] < ttl:
        return json.loads(rows[0][0])
    return None


def session_put(key: str, events: list) -> None:
    _q("INSERT OR REPLACE INTO session_cache VALUES (?,?,?)", (key, json.dumps(events), time.time()))


# ── Spend ledger / rate limit ────────────────────────────────────────────────
def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def spend_add(cost: float) -> None:
    if cost > 0:
        _q("INSERT INTO ledger (day, cost, ts) VALUES (?,?,?)", (_today(), cost, time.time()))


def spend_today() -> float:
    rows = _q("SELECT COALESCE(SUM(cost),0) FROM ledger WHERE day=?", (_today(),))
    return float(rows[0][0])


def rate_check_and_log(ip: str, limit: int, window_s: int) -> tuple[bool, int]:
    """Record a run for `ip`; returns (allowed, retry_after_seconds)."""
    now = time.time()
    _q("DELETE FROM rate_log WHERE ts < ?", (now - window_s,))
    rows = _q("SELECT ts FROM rate_log WHERE ip=? ORDER BY ts", (ip,))
    if len(rows) >= limit:
        return False, int(rows[0][0] + window_s - now) + 1
    _q("INSERT INTO rate_log VALUES (?,?)", (ip, now))
    return True, 0
