"""Read agent activity from OpenCode's SQLite, read-only.

OpenCode has two storage generations on disk: `session_v2` + `session_message`
(the bulk of history) and a newer `session` + `message` pair. The union of
both is what `join.py` needs: any activity within ±120 s of an omniroute
request points that request at the session's project directory. Usage itself
is never read here — tokens and cost live only in the omniroute ledger.
"""

from __future__ import annotations

import sqlite3


def read_activity(path: str) -> list[dict]:
    """[(ts, session_oid, project, title)] — one row per message, sorted."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        queries = []
        if {"session_message", "session_v2"} <= tables:
            queries.append(
                "SELECT m.time_created, m.session_id, s.directory, s.title"
                " FROM session_message m JOIN session_v2 s"
                "   ON s.id = m.session_id")
        if {"message", "session"} <= tables:
            queries.append(
                "SELECT m.time_created, m.session_id, s.directory, s.title"
                " FROM message m JOIN session s ON s.id = m.session_id")
        if not queries:
            return []
        rows = db.execute(" UNION ALL ".join(queries) + " ORDER BY 1").fetchall()
    finally:
        db.close()
    return [dict(ts=row[0], session_oid=row[1], project=row[2], title=row[3])
            for row in rows]
