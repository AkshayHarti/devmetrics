"""`devmetrics sync` and the views it feeds.

Semantics agreed in docs/specs/2026-10-25-devmetrics.md:
- omniroute's request_cost_ledger is the source of truth, read-only;
- a request is attributed to the project of any session that was active
  within ±120 s; exactly one distinct project gets the row, otherwise it
  stays unattributed rather than guessed (ntfsmnt's no-guesses rule);
- sync is idempotent, so it can run after every session.
"""

from __future__ import annotations

import sqlite3

import pytest

from devmetrics.cli import main
from tests.sources import make_opencode, make_omniroute, message, request

T0 = 1_800_000_000_000
WINDOW_MS = 120_000


def args_for(tmp_path, *, rows=None, sessions=None, messages=None):
    omni = tmp_path / "omni.sqlite"
    open_db = tmp_path / "opencode.sqlite"
    make_omniroute(str(omni), rows if rows is not None else [
        request(T0 + 500, rid="r1"),
        request(T0 + 60_000, rid="r2"),
    ])
    make_opencode(str(open_db),
                  sessions if sessions is not None else
                  [("s1", "p1", "hd1-mount", "/repos/ntfs-mounter",
                    "HD1 acceptance")],
                  messages if messages is not None else
                  [message("s1", T0), message("s1", T0 + 1_000)])
    return (["--omniroute", str(omni), "--opencode", str(open_db),
             "--warehouse", str(tmp_path / "devmetrics.sqlite")])


def warehouse_rows(warehouse, table="requests"):
    db = sqlite3.connect(warehouse)
    db.row_factory = sqlite3.Row
    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    db.close()
    return rows


def test_sync_attributes_requests_from_nearby_sessions(tmp_path) -> None:
    args = args_for(tmp_path)
    assert main([*args, "sync"]) == 0
    rows = sorted(warehouse_rows(tmp_path / "devmetrics.sqlite"),
                  key=lambda r: r["ts"])

    assert [(r["rid"], r["project"], r["session_oid"], r["title"])
            for r in rows] == [
        ("r1", "/repos/ntfs-mounter", "s1", "HD1 acceptance"),
        ("r2", "/repos/ntfs-mounter", "s1", "HD1 acceptance"),
    ]
    assert all(r["amount_usd"] == pytest.approx(0.01) for r in rows)
    assert all(r["t_in"] == 100 and r["t_out"] == 50 for r in rows)


def test_sync_is_idempotent(tmp_path) -> None:
    args = args_for(tmp_path)
    assert main([*args, "sync"]) == 0
    assert main([*args, "sync"]) == 0
    assert len(warehouse_rows(tmp_path / "devmetrics.sqlite")) == 2


def test_sync_refuses_to_guess_between_projects(tmp_path) -> None:
    # Two projects are active in the window: nobody picks.
    sessions = [("s1", "p1", "hd1-mount", "/repos/ntfs-mounter", "HD1"),
                ("s2", "p2", "other", "/repos/other", "Other")]
    messages = [message("s1", T0), message("s2", T0, path="/repos/other")]
    args = args_for(tmp_path, sessions=sessions, messages=messages)
    assert main([*args, "sync"]) == 0
    projects = {r["rid"]: r["project"]
                for r in warehouse_rows(tmp_path / "devmetrics.sqlite")}
    assert projects == {"r1": None, "r2": None}


def test_sync_marks_gaps_unattributed(tmp_path) -> None:
    args = args_for(tmp_path, rows=[
        request(T0 + 500, rid="near"),
        request(T0 + 3 * WINDOW_MS, rid="gap"),
    ])
    assert main([*args, "sync"]) == 0
    projects = {r["rid"]: r["project"]
                for r in warehouse_rows(tmp_path / "devmetrics.sqlite")}
    assert projects == {"near": "/repos/ntfs-mounter", "gap": None}


def test_cost_prints_project_totals(tmp_path, capsys) -> None:
    args = args_for(tmp_path)
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "cost"]) == 0
    out = capsys.readouterr().out
    assert "ntfs-mounter" in out
    assert "$0.02" in out
    assert "200" in out and "100" in out  # input tokens, output tokens


def test_cost_not_before_gaps_are_unattributed(tmp_path, capsys) -> None:
    args = args_for(tmp_path, rows=[request(T0 + 3 * WINDOW_MS, rid="gap")])
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "cost"]) == 0
    out = capsys.readouterr().out
    assert "unattributed" in out
    assert "$0.01" in out


def test_cost_since_pare_filter(tmp_path, capsys) -> None:
    args = args_for(tmp_path, rows=[request(T0, rid="r1", amount=0.9)])
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    # 1 day back includes today's request; a date in the past excludes it.
    assert main([*args, "cost", "--since", "1d"]) == 0
    assert "$0.90" in capsys.readouterr().out
    assert main([*args, "cost", "--since", "3000-01-01"]) == 0
    assert "$0.90" not in capsys.readouterr().out


def test_models_view(tmp_path, capsys) -> None:
    args = args_for(tmp_path, rows=[
        request(T0 + 500, rid="ok", amount=0.01),
        request(T0 + 600, rid="bad", amount=0.0, success=0),
    ])
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "models"]) == 0
    out = capsys.readouterr().out
    assert "gpt" in out
    assert "50%" in out  # 1 of 2 gpt requests succeeded
    assert "$0.01" in out


def test_label_is_recorded_and_replaced(tmp_path, capsys) -> None:
    args = args_for(tmp_path)
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest", "good"]) == 0
    assert main([*args, "sessions"]) == 0
    out = capsys.readouterr().out
    assert "good" in out and "HD1 acceptance" in out
    assert main([*args, "label", "latest", "rework"]) == 0
    assert main([*args, "sessions"]) == 0
    out = capsys.readouterr().out
    assert "rework" in out
    assert "good" not in out


def test_label_rejects_unknown_values(tmp_path) -> None:
    args = args_for(tmp_path)
    assert main([*args, "sync"]) == 0
    assert main([*args, "label", "latest", "amazing"]) == 4
    assert not [r for r in warehouse_rows(
        tmp_path / "devmetrics.sqlite", "labels")]
