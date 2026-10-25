"""Evidence for end-of-session labels, read from the harness log.

The verdict is deliberately not an LLM: the proposal is deterministic
evidence ("corrections after work", "tool errors") so the human's one-tap
confirm — or override — stays the quality bar. An LLM rating its own output
always knows which label sounds good.
"""

from __future__ import annotations

import json
import sqlite3


def read_evidence(path: str, session_oid: str) -> dict:
    """user turns and tool errors within one session, from session logs."""
    counts = {"user": 0, "tool_errors": 0}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "session_message" not in tables:
            return counts  # old-generation session rows carry no evidence
        rows = db.execute(
            "SELECT type, data FROM session_message"
            " WHERE session_id = ? ORDER BY seq", (session_oid,)).fetchall()
    finally:
        db.close()
    for kind, raw in rows:
        if kind == "user":
            counts["user"] += 1
        elif kind == "assistant":
            try:
                content = json.loads(raw).get("content") or []
            except json.JSONDecodeError:
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool" \
                        and (part.get("state") or {}).get("status") == "error":
                    counts["tool_errors"] += 1
    return counts


def propose(evidence: dict) -> tuple[str, list[str]]:
    user = evidence["user"]
    errors = evidence["tool_errors"]
    reasons = []
    if user >= 3:
        reasons.append(f"{user} check-ins after working")
    if errors:
        reasons.append(f"{errors} tool errors")
    if user >= 3 and errors >= 3 or errors >= 10:
        label = "rework"
    elif user >= 3 or errors >= 1:
        label = "meh"
    else:
        label = "good"
    return label, reasons or ["no corrections, no tool errors"]
