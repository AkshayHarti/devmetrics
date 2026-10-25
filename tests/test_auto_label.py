"""Auto-label: evidence from the session log proposes; the human confirms.

Rules pinned here (see docs/specs/2026-10-25-devmetrics.md — "propose,
human executes" is the ntfsmnt agent contract reused):
  - the proposal is deterministic evidence, never an LLM verdict;
  - `label <target> <label>` is always accepted even if it differs from the
    proposal — the human wins;
  - `label <target> --yes` accepts the proposal, recording source=accepted;
  - a non-interactive run without --yes or an explicit label only prints
    the proposal and exits 0, changing nothing.
"""

from __future__ import annotations

import sqlite3

from devmetrics.cli import main
from devmetrics.store import connect
from tests.evidence_fixtures import (clean_session, corrected_session,
                                     failing_session, make_v2)
from tests.sources import make_omniroute, request

T0 = 1_800_000_000_000


def setup(tmp_path, messages) -> list[str]:
    omni = tmp_path / "omni.sqlite"
    v2 = tmp_path / "opencode.sqlite"
    make_omniroute(str(omni), [request(T0 + 500)])
    # s2 sits at another project in the same window, so the attribution rule
    # (no guessing) would null the row — only s1's messages are in the binary
    make_v2(str(v2), [("s1", "/repos/ntfs-mounter", "HD1 acceptance")],
            list(messages))
    return ["--omniroute", str(omni), "--opencode", str(v2),
            "--warehouse", str(tmp_path / "devmetrics.sqlite")]


def test_bare_label_defaults_to_latest(tmp_path, capsys) -> None:
    args = setup(tmp_path, clean_session())
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "--yes"]) == 0
    out = capsys.readouterr().out
    assert "proposed: good" in out and "accepted" in out


def test_proposal_good_for_a_clean_session(tmp_path, capsys) -> None:
    args = setup(tmp_path, clean_session())
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest"]) == 0
    out = capsys.readouterr().out
    assert "proposed: good" in out
    # nothing was recorded; a non-interactive run only reports
    db = connect(str(tmp_path / "devmetrics.sqlite"))
    assert not db.execute("SELECT * FROM labels").fetchall()
    db.close()


def test_proposal_meh_for_corrections(tmp_path, capsys) -> None:
    args = setup(tmp_path, corrected_session())
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest"]) == 0
    out = capsys.readouterr().out
    assert "proposed: meh" in out
    assert "check-ins after working" in out


def test_proposal_rework_for_error_storms(tmp_path, capsys) -> None:
    args = setup(tmp_path, failing_session())
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest"]) == 0
    out = capsys.readouterr().out
    assert "proposed: rework" in out
    assert "tool errors" in out


def test_yes_accepts_the_proposal(tmp_path, capsys) -> None:
    args = setup(tmp_path, clean_session())
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest", "--yes"]) == 0
    out = capsys.readouterr().out
    assert "proposed: good" in out and "accepted" in out
    db = connect(str(tmp_path / "devmetrics.sqlite"))
    labels = db.execute("SELECT label, source FROM labels").fetchall()
    db.close()
    assert [(r["label"], r["source"]) for r in labels] == [("good", "accepted")]


def test_explicit_label_always_wins(tmp_path, capsys) -> None:
    args = setup(tmp_path, failing_session())  # evidence screams rework
    assert main([*args, "sync"]) == 0
    capsys.readouterr()
    assert main([*args, "label", "latest", "rework"]) == 0
    db = connect(str(tmp_path / "devmetrics.sqlite"))
    rows = db.execute("SELECT label, source FROM labels").fetchall()
    db.close()
    assert [(r["label"], r["source"]) for r in rows] == [("rework", "manual")]


def test_older_warehouses_gain_the_source_column(tmp_path) -> None:
    # A warehouse written by 0.1.0 has labels without `source`; connect must
    # add the column and keep the rows.
    warehouse = tmp_path / "devmetrics.sqlite"
    db = sqlite3.connect(warehouse)
    db.executescript(
        "CREATE TABLE labels (session_oid TEXT PRIMARY KEY, project TEXT,"
        " title TEXT, label TEXT NOT NULL, at INTEGER NOT NULL);"
        " INSERT INTO labels VALUES"
        " ('s1','/p','t','good',1);")
    db.commit()
    db.close()
    omni = tmp_path / "omni.sqlite"; v2 = tmp_path / "opencode.sqlite"
    make_omniroute(str(omni), [request(T0 + 500)])
    make_v2(str(v2), [("s1", "/repos/other", "Other")], [])
    assert main(["--omniroute", str(omni), "--opencode", str(v2),
                 "--warehouse", str(warehouse), "sessions"]) == 0
    db = sqlite3.connect(warehouse)
    rows = db.execute("SELECT label, source FROM labels").fetchall()
    db.close()
    assert rows == [("good", "manual")]
