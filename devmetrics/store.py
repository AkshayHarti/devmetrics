"""The local warehouse: devmetrics' own SQLite, written only by `sync`.

One table per idea, no migrations beyond the first schema:
- requests: one row per omniroute request, attributed (or not) to a project.
- labels:   one row per session, the human's end-of-session taste.
- sync_state: watermark so a second sync never re-reads history (kept simple:
              replace-all on requests; labels are never derived).
"""

from __future__ import annotations

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  rid TEXT PRIMARY KEY,
  ts INTEGER NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  t_in INTEGER NOT NULL,
  t_out INTEGER NOT NULL,
  t_cache_read INTEGER NOT NULL,
  t_cache_write INTEGER NOT NULL,
  t_reasoning INTEGER NOT NULL,
  amount_usd REAL NOT NULL,
  success INTEGER NOT NULL,
  tier TEXT NOT NULL,
  api_key TEXT NOT NULL,
  project TEXT,
  session_oid TEXT,
  title TEXT
);
CREATE TABLE IF NOT EXISTS labels (
  session_oid TEXT PRIMARY KEY,
  project TEXT,
  title TEXT,
  label TEXT NOT NULL CHECK (label IN ('good', 'meh', 'rework')),
  at INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_TYPES = (str, int, str, str, int, int, int, int, int, float, int, str, str,
          str, str, str, str)
_COLS = ("rid", "ts", "provider", "model", "t_in", "t_out", "t_cache_read",
         "t_cache_write", "t_reasoning", "amount_usd", "success", "tier",
         "api_key", "project", "session_oid", "title")


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    _migrate(db)
    return db


def _migrate(db: sqlite3.Connection) -> None:
    # 0.1.0 warehouses predate the source column on labels.
    columns = {row[1] for row in db.execute("PRAGMA table_info(labels)")}
    if "source" not in columns:
        db.execute(
            "ALTER TABLE labels ADD COLUMN source TEXT NOT NULL"
            " DEFAULT 'manual'")
        db.commit()


def save_requests(db: sqlite3.Connection, requests: list[dict]) -> None:
    db.execute("DELETE FROM requests")
    db.executemany(
        "INSERT OR REPLACE INTO requests (" + ",".join(_COLS) + ")"
        " VALUES (" + ",".join("?" * len(_COLS)) + ")",
        [_row(request) for request in requests])
    db.commit()


def _row(request: dict) -> tuple:
    return (
        request["rid"] or f"ts-{request['ts']}-{request['model']}",
        request["ts"], request["provider"], request["model"],
        request["t_in"], request["t_out"], request["t_cache_read"],
        request["t_cache_write"], request["t_reasoning"],
        request["amount_usd"], int(request["success"]), request["tier"],
        request["api_key"], request["project"], request["session_oid"],
        request["title"],
    )


def set_label(db: sqlite3.Connection, session_oid: str, label: str,
              source: str = "manual") -> None:
    row = db.execute(
        "SELECT project, title FROM requests WHERE session_oid = ? LIMIT 1",
        (session_oid,)).fetchone()
    db.execute(
        "INSERT INTO labels (session_oid, project, title, label, at, source)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(session_oid) DO UPDATE SET"
        " project=excluded.project, title=excluded.title,"
        " label=excluded.label, at=excluded.at, source=excluded.source",
        (session_oid, row["project"] if row else None,
         row["title"] if row else None, label, int(time.time() * 1000),
         source))
    db.commit()


def last_sync(db: sqlite3.Connection) -> str | None:
    row = db.execute("SELECT value FROM kv WHERE key = 'synced_at'").fetchone()
    return row["value"] if row else None


def mark_sync(db: sqlite3.Connection, stamp: str) -> None:
    db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES ('synced_at',?)",
               (stamp,))
    db.commit()


def json_kv(row: sqlite3.Row) -> dict:
    return json.loads(json.dumps({k: row[k] for k in row.keys()}))
