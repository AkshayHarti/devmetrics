"""Needed fixtures and the auto-label contract.

`refine-make` presents a Zusammenfassung of each Projekt.

The proposal is evidence-based and never autonomous: an LLM rating its own
work is predictably biased. Actions:
  - explicit `devmetrics label latest good` records it with source='manual';
  - `devmetrics label latest --yes` accepts the proposal, source='accepted';
  - shown reasons always accompany the proposal, so each tap stays auditable.
"""

from __future__ import annotations

import json
import sqlite3

V2_SCHEMA = """
CREATE TABLE session_v2 (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, slug TEXT NOT NULL,
  directory TEXT NOT NULL, title TEXT NOT NULL
);
CREATE TABLE session_message (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
  seq INTEGER NOT NULL, time_created INTEGER NOT NULL,
  type TEXT NOT NULL, data TEXT NOT NULL
);
"""


def make_v2(path, sessions, messages):
    """sessions: [(id, dir, title)]; messages: [(sid, seq, ts, type, data)]"""
    db = sqlite3.connect(path)
    db.executescript(V2_SCHEMA)
    db.executemany("INSERT INTO session_v2 (id, project_id, slug, directory,"
                   " title) VALUES (?,?,?,?,?)",
                   [(sid, f"p-{sid}", sid, directory, title)
                    for sid, directory, title in sessions])
    db.executemany("INSERT INTO session_message (id, session_id, seq,"
                   " time_created, type, data) VALUES (?,?,?,?,?,?)",
                   messages)
    db.commit()
    db.close()


def ts(i: int) -> int:
    return 1_800_000_000_000 + i * 1_000


def clean_session(sid="s1", path="/repos/ntfs-mounter") -> tuple:
    """One user ask, a bit of tool work, no errors."""
    rows = [
        (f"{sid}-u", sid, 1, ts(0), "user",
         json.dumps({"text": "build the thing"})),
        (f"{sid}-a1", sid, 2, ts(1), "assistant",
         json.dumps({"content": [
             {"type": "tool", "state": {"status": "running"}}]})),
        (f"{sid}-a2", sid, 3, ts(2), "assistant",
         json.dumps({"content": [{"type": "text",
                                  "text": "done, tests green"}]})),
    ]
    return rows


def corrected_session(sid="s1", path="/repos/ntfs-mounter") -> tuple:
    """User keeps pushing after the claim: 4 user turns, no tool errors."""
    rows = [(f"{sid}-u{i}", sid, i + 1, ts(i), "user",
             json.dumps({"text": "no, still wrong"}))
            for i in range(4)]
    rows.append((f"{sid}-a", sid, 9, ts(9), "assistant",
                 json.dumps({"content": [{"type": "text", "text": "ok now"}]})))
    return rows


def failing_session(sid="s1", path="/repos/ntfs-mounter") -> tuple:
    """Heavy tool errors: the session that screams rework."""
    rows = []
    for i in range(6):
        rows.append((f"{sid}-u{i}", sid, i * 2 + 1, ts(i * 2), "user",
                     json.dumps({"text": "fix it"})))
        rows.append((f"{sid}-e{i}", sid, i * 2 + 2, ts(i * 2 + 1), "assistant",
                     json.dumps({"content": [
                         {"type": "tool", "state": {"status": "error"}}]})))
    return rows
