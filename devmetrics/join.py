"""Attribute omniroute requests to projects via session activity windows.

Iron rule (from ntfsmnt, applied to bookkeeping): a request with two
distinct candidate projects stays unattributed. Nearest-session guessing is
how "shared hours" get billed to the wrong feature.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

WINDOW_MS = 120_000


def attribute(requests: list[dict], activity: list[dict]) -> None:
    """Adds project / session_oid / title to each request dict in place."""
    times = [row["ts"] for row in activity]
    for request in requests:
        low = bisect_left(times, request["ts"] - WINDOW_MS)
        high = bisect_right(times, request["ts"] + WINDOW_MS)
        candidates = activity[low:high]
        projects = {row["project"] for row in candidates}
        if len(projects) == 1:
            nearest = min(candidates,
                          key=lambda row: abs(row["ts"] - request["ts"]))
            request["project"] = nearest["project"]
            request["session_oid"] = nearest["session_oid"]
            request["title"] = nearest["title"]
        else:
            request["project"] = None
            request["session_oid"] = None
            request["title"] = None
