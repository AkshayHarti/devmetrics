"""The devmetrics command line.

    devmetrics [--omniroute DB] [--opencode DB] [--warehouse DB] <command>

Defaults point at the real sources on this machine; tests and other setups
pass paths explicitly. Subcommands:

    sync      refresh the warehouse (idempotent)
    cost      money view, grouped by project ("unattributed" is a group)
    models    requests, success rate, and dollars per model
    sessions  session table with labels
    label     latest|<session-oid> good|meh|rework
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from devmetrics import evidence, store
from devmetrics.join import attribute
from devmetrics.sources import omniroute, opencode

LABELS = ("good", "meh", "rework")


def _default(name: str) -> str:
    return str(Path.home() / name)


def _parse_since(value: str) -> int:
    """--since takes Nd (days back) or a YYYY-MM-DD cutoff; returns epoch ms.
    A single '0' means no filter."""
    if value == "0":
        return 0
    if value.endswith("d"):
        stamp = datetime.now() - timedelta(days=int(value[:-1] or "1"))
        return int(stamp.timestamp() * 1000)
    stamp = datetime.combine(
        date.fromisoformat(value), datetime.min.time()).astimezone()
    return int(stamp.timestamp() * 1000)


def cmd_sync(args) -> int:
    requests = omniroute.read_requests(args.omniroute)
    activity = opencode.read_activity(args.opencode)
    attribute(requests, activity)
    db = store.connect(args.warehouse)
    store.save_requests(db, requests)
    store.mark_sync(db, datetime.now(timezone.utc).isoformat())
    db.close()
    print(f"synced {len(requests)} requests + {len(activity)} activity rows"
          f" -> {args.warehouse}")
    return 0


def _sum_rows(db: sqlite3.Connection, sql: str, params=()) -> list[sqlite3.Row]:
    return db.execute(sql, params).fetchall()


def cmd_cost(args) -> int:
    cutoff = _parse_since(args.since)
    db = store.connect(args.warehouse)
    rows = _sum_rows(db, """
        SELECT COALESCE(project, 'unattributed') AS bucket,
               COUNT(*) AS requests,
               SUM(t_in) AS t_in, SUM(t_out) AS t_out,
               SUM(amount_usd) AS usd
        FROM requests WHERE success = 1 AND (:cutoff = 0 OR ts >= :cutoff)
        GROUP BY bucket ORDER BY usd DESC""", {"cutoff": cutoff})
    for row in rows:
        name = "unattributed" if row["bucket"] == "unattributed" \
            else Path(row["bucket"]).name
        print(f"{name:<24} {row['t_in'] or 0:>12} in  {row['t_out'] or 0:>12}"
              f" out  ${row['usd'] or 0:.2f}  ({row['requests']} requests)")
    db.close()
    return 0


def cmd_models(args) -> int:
    cutoff = _parse_since(args.since)
    db = store.connect(args.warehouse)
    rows = _sum_rows(db, """
        SELECT model, COUNT(*) AS requests,
               SUM(success) AS ok, SUM(amount_usd) AS usd
        FROM requests WHERE (:cutoff = 0 OR ts >= :cutoff)
        GROUP BY model ORDER BY usd DESC""", {"cutoff": cutoff})
    for row in rows:
        rate = 100 * row["ok"] / row["requests"]
        print(f"{row['model']:<32} {row['requests']:>6} requests"
              f"  {rate:>5.0f}% ok  ${row['usd'] or 0:.2f}")
    db.close()
    return 0


def cmd_sessions(args) -> int:
    cutoff = _parse_since(args.since)
    db = store.connect(args.warehouse)
    rows = _sum_rows(db, """
        SELECT session_oid, MIN(ts) AS first_ts, COUNT(*) AS requests,
               SUM(amount_usd) AS usd, title, project
        FROM requests
        WHERE session_oid IS NOT NULL AND (:cutoff = 0 OR ts >= :cutoff)
        GROUP BY session_oid ORDER BY first_ts""", {"cutoff": cutoff})
    labels = {r["session_oid"]: r["label"]
              for r in db.execute("SELECT session_oid, label FROM labels")}
    for row in rows:
        tagged = f"  [{labels[row['session_oid']]}]" \
            if row["session_oid"] in labels else ""
        print(f"{row['title'] or '(untitled)':<40} {row['requests']:>6} req"
              f"  ${row['usd'] or 0:.2f}{tagged}")
    db.close()
    return 0


def cmd_label(args) -> int:
    explicit, accept = args.label, args.yes
    if explicit and explicit not in LABELS:
        print(f"error: label must be one of {', '.join(LABELS)}",
              file=sys.stderr)
        return 4
    db = store.connect(args.warehouse)
    try:
        if args.target != "latest":
            oid = args.target
        else:
            row = db.execute(
                "SELECT session_oid FROM requests WHERE session_oid IS NOT"
                " NULL ORDER BY ts DESC LIMIT 1").fetchone()
            if not row:
                print("error: no attributed sessions yet — run"
                      " `devmetrics sync`", file=sys.stderr)
                return 3
            oid = row["session_oid"]

        proposal, reasons = evidence.propose(
            evidence.read_evidence(args.opencode, oid))
        if explicit:
            store.set_label(db, oid, explicit, source="manual")
            print(f"recorded {oid[:8]}: {explicit} (manual;"
                  f" evidence proposed {proposal})")
            return 0

        print(f"proposed: {proposal}"
              f" ({oid[:8]}…; {'; '.join(reasons)})")
        if accept:
            store.set_label(db, oid, proposal, source="accepted")
            print("accepted")
            return 0
        if sys.stdin.isatty():
            answer = input("Enter=accept, 1=good 2=meh 3=rework, n=skip: ")
            if answer in ("", "1", "2", "3"):
                chosen = {1: "good", 2: "meh", 3: "rework"}[int(answer)]
                store.set_label(db, oid, chosen, source="accepted"
                                if chosen == proposal else "manual")
                print("accepted" if chosen == proposal
                      else f"recorded {oid[:8]}: {chosen} (manual)")
                return 0
            if answer == "n":
                print("left unlabeled")
                return 0
        else:
            print("not interactive: confirm with --yes or an explicit"
                  " good|meh|rework")
        return 0
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devmetrics", description=__doc__)
    parser.add_argument("--omniroute", default=_default(".omniroute/storage.sqlite"))
    parser.add_argument("--opencode", default=_default(".local/share/opencode/opencode.db"))
    parser.add_argument("--warehouse", default=os.environ.get(
        "DEVMETRICS_WAREHOUSE", _default(".local/share/devmetrics/ledger.sqlite")))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync").set_defaults(func=cmd_sync)
    for name, func in (("cost", cmd_cost), ("models", cmd_models),
                       ("sessions", cmd_sessions)):
        view = sub.add_parser(name)
        view.add_argument("--since", default="0")
        view.set_defaults(func=func)
    label = sub.add_parser("label")
    label.add_argument("target")
    label.add_argument("label", nargs="?", default=None)
    label.add_argument("--yes", action="store_true",
                       help="accept the current proposal")
    label.set_defaults(func=cmd_label)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
