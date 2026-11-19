#!/usr/bin/env python3
"""Seat pacing check (RELIABLE-01 R04, finding E-05). Report only.

Counts rate-limit lines per seat in a time window, by shape, two classes kept
apart (the usage-cap class and the fast-mode credit class), plus the leader
"hit your N-hour limit" lines in the dispatch run logs (by file mtime).
It keeps counts only: no line text is printed, stored or returned. It sends
nothing, writes no file and touches no seat or service.

Exit 0: every row OK or ABSENT. Exit 1: some row is SLOW, PAUSE or CREDIT.
Exit 2: a configured log exists but cannot be read.
"""
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---- config block -----------------------------------------------------------
SEATS = ("hub", "hades", "hephaestus", "poseidon", "zeus")
HERMES_HOME = Path.home() / "AppData" / "Local" / "hermes"   # SEAT_PACING_HOME
HUB_LOG = Path("logs") / "agent.log"                         # hub, under the home
PROFILE_LOG = Path("logs") / "agent.log"                     # others, under profiles/<seat>
DISPATCH_DIR = Path.home() / ".loop" / "dispatch"            # SEAT_PACING_DISPATCH
WINDOW_HOURS = 24.0                                          # SEAT_PACING_HOURS
SLOW_AT = 1                                                  # cap-class lines for SLOW
PAUSE_AT = 5                                                 # cap-class lines for PAUSE
# SEAT_PACING_NOW: a fixed "now" (ISO, local time) for tests
# -----------------------------------------------------------------------------

TS_RE = re.compile(rb"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
RL_MARK = b"rate_limit_error"
CODE_MARK = b"429"
CREDIT_MARK = b"Usage credits are required for fast mode"
LEADER_RE = re.compile(rb"hit your \d+-hour limit")


def line_time(line):
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime(*[int(g) for g in m.groups()])
    except ValueError:
        return None


def classify(line):
    """Return 'cap', 'credit' or None. Shape only; the text is never kept."""
    if RL_MARK not in line or CODE_MARK not in line:
        return None
    if CREDIT_MARK in line:
        return "credit"
    return "cap"


def count_agent_log(path, start, now):
    cap = credit = 0
    with open(path, "rb") as fh:
        for line in fh:
            kind = classify(line)
            if kind is None:
                continue
            ts = line_time(line)
            if ts is None or ts < start or ts > now:
                continue
            if kind == "cap":
                cap += 1
            else:
                credit += 1
    return cap, credit


def count_leader(folder, start, now):
    n = 0
    for entry in sorted(os.listdir(folder)):
        p = Path(folder) / entry
        if not p.is_file():
            continue
        mtime = datetime.fromtimestamp(os.path.getmtime(p))
        if mtime < start or mtime > now:
            continue
        with open(p, "rb") as fh:
            for line in fh:
                if LEADER_RE.search(line):
                    n += 1
    return n


def verdict(cap, credit):
    if cap >= PAUSE_AT:
        return "PAUSE"
    if cap >= SLOW_AT:
        return "SLOW"
    if credit > 0:
        return "CREDIT"
    return "OK"


def settings():
    home = Path(os.environ.get("SEAT_PACING_HOME") or HERMES_HOME)
    dispatch = Path(os.environ.get("SEAT_PACING_DISPATCH") or DISPATCH_DIR)
    hours = WINDOW_HOURS
    raw = os.environ.get("SEAT_PACING_HOURS")
    if raw:
        try:
            hours = float(raw)
        except ValueError:
            pass
    now = datetime.now()
    raw = os.environ.get("SEAT_PACING_NOW")
    if raw:
        try:
            now = datetime.fromisoformat(raw)
        except ValueError:
            pass
    return home, dispatch, hours, now


def seat_log(home, seat):
    if seat == "hub":
        return home / HUB_LOG
    return home / "profiles" / seat / PROFILE_LOG


def main():
    home, dispatch, hours, now = settings()
    start = now - timedelta(hours=hours)
    rows = []
    unreadable = False
    for seat in SEATS:
        path = seat_log(home, seat)
        if not path.exists():
            rows.append((seat, "-", "-", "ABSENT"))
            continue
        try:
            cap, credit = count_agent_log(path, start, now)
        except OSError:
            unreadable = True
            rows.append((seat, "-", "-", "UNREADABLE"))
            continue
        rows.append((seat, cap, credit, verdict(cap, credit)))
    if not dispatch.exists():
        rows.append(("leader", "-", "-", "ABSENT"))
    else:
        try:
            n = count_leader(dispatch, start, now)
            rows.append(("leader", n, "-", verdict(n, 0)))
        except OSError:
            unreadable = True
            rows.append(("leader", "-", "-", "UNREADABLE"))
    cap_total = sum(r[1] for r in rows if isinstance(r[1], int))
    credit_total = sum(r[2] for r in rows if isinstance(r[2], int))
    not_ok = sum(1 for r in rows if r[3] not in ("OK", "ABSENT"))
    for seat, cap, credit, v in rows:
        print("seat=%s cap=%s credit=%s verdict=%s" % (seat, cap, credit, v))
    print("total rows=%d not_ok=%d cap=%d credit=%d window_hours=%g"
          % (len(rows), not_ok, cap_total, credit_total, hours))
    if unreadable:
        return 2
    return 1 if not_ok else 0


if __name__ == "__main__":
    sys.exit(main())
