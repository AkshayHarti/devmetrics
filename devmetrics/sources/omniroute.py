"""Read the omniroute request ledger, read-only.

Everything on this machine routes LLM calls through omniroute, and its
`request_cost_ledger` is the single record of tokens and money. This module
only *reads* SQLite and normalizes timestamps to epoch milliseconds; it
never writes to the omniroute database.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _ts_ms(value: str) -> int:
    ts_text = value[:-1] if value.endswith("Z") else value
    ts_date = datetime.fromisoformat(ts_text).replace(tzinfo=timezone.utc)
    return int(ts_date.timestamp() * 1000)


def read_requests(path: str) -> list[dict]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT provider, model, tokens_input, tokens_output,"
            " tokens_cache_read, tokens_cache_creation, tokens_reasoning,"
            " amount_usd, success, service_tier, api_key_id, timestamp,"
            " request_id FROM request_cost_ledger").fetchall()
    finally:
        db.close()
    return [dict(provider=row[0], model=row[1], t_in=row[2], t_out=row[3],
                 t_cache_read=row[4], t_cache_write=row[5], t_reasoning=row[6],
                 amount_usd=row[7], success=bool(row[8]), tier=row[9],
                 api_key=row[10], ts=_ts_ms(row[11]), rid=row[12])
            for row in rows]
