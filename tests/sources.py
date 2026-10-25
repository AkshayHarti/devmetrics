"""Fixture builders: fake omniroute and opencode SQLite databases.

They only create the columns devmetrics reads, so the real schemas can grow
without touching these tests.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

OMNI_SCHEMA = """
CREATE TABLE request_cost_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  api_key_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  tokens_input INTEGER NOT NULL DEFAULT 0,
  tokens_output INTEGER NOT NULL DEFAULT 0,
  tokens_cache_read INTEGER NOT NULL DEFAULT 0,
  tokens_cache_creation INTEGER NOT NULL DEFAULT 0,
  tokens_reasoning INTEGER NOT NULL DEFAULT 0,
  unit_price_input REAL NOT NULL DEFAULT 0,
  unit_price_output REAL NOT NULL DEFAULT 0,
  amount_usd REAL NOT NULL DEFAULT 0,
  service_tier TEXT NOT NULL DEFAULT 'standard',
  success INTEGER NOT NULL DEFAULT 1,
  timestamp TEXT NOT NULL,
  request_id TEXT
);
"""

# OpenCode stores times as milliseconds since the epoch in a TEXT `timestamp`
# column on omniroute and INTEGER time_created on opencode; both sides are
# normalized to epoch milliseconds by the source readers.
OPENCODE_SCHEMA = """
CREATE TABLE session (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  slug TEXT NOT NULL,
  directory TEXT NOT NULL,
  title TEXT NOT NULL
);
CREATE TABLE message (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  time_created INTEGER NOT NULL,
  data TEXT NOT NULL
);
"""


def make_omniroute(path, rows) -> None:
    db = sqlite3.connect(path)
    db.executescript(OMNI_SCHEMA)
    db.executemany(
        "INSERT INTO request_cost_ledger"
        "(api_key_id, provider, model, tokens_input, tokens_output,"
        " tokens_cache_read, tokens_cache_creation, tokens_reasoning,"
        " unit_price_input, unit_price_output, amount_usd, service_tier,"
        " success, timestamp, request_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    db.commit()
    db.close()


def make_opencode(path, sessions, messages) -> None:
    db = sqlite3.connect(path)
    db.executescript(OPENCODE_SCHEMA)
    db.executemany(
        "INSERT INTO session (id, project_id, slug, directory, title)"
        " VALUES (?,?,?,?,?)",
        sessions,
    )
    db.executemany(
        "INSERT INTO message (id, session_id, time_created, data) VALUES (?,?,?,?)",
        messages,
    )
    db.commit()
    db.close()


def message(session_id: str, ts_ms: int, *, path="/repos/ntfs-mounter",
            tokens=(100, 50), model="gpt") -> tuple:
    data = json.dumps({
        "path": {"cwd": path},
        "tokens": {"input": tokens[0], "output": tokens[1]},
        "modelID": model,
    })
    return (f"m-{ts_ms}-{session_id}", session_id, ts_ms, data)


def request(ts_ms: int, *, amount=0.01, model="gpt", success=1, key="k",
            rid="r1") -> tuple:
    stamp = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
    timestamp = stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts_ms % 1000:03d}Z"
    return (key, "prov", model, 100, 50, 0, 0, 0, 0.0, 0.0, amount,
            "standard", success, timestamp, rid)
