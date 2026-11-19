"""Report-only watch on the hub's Telegram link (RELIABLE-01 R06, finding E-10).

Reads a gateway log line by line, keeps the lines whose timestamp falls inside the window, and
counts them by shape: network warnings, degraded polls, degraded reconnects, reconnects, connects.
Prints one "<shape> <count>" line per shape and one verdict line. It keeps counts only: no line
text is printed, stored or returned. Lines of the shape "inbound message" carry a display name, a
chat id and message text; they are dropped before any other test, never matched or counted.
It sends nothing and writes no file.

Exit codes: 0 OK, 1 ALERT, 2 the log (or a setting) cannot be read.
Environment overrides: HUB_TG_LOG (log path), HUB_TG_HOURS (window), HUB_TG_NOW (test clock,
"YYYY-MM-DD HH:MM:SS", read only when set).
"""
import datetime
import os
import pathlib
import re
import sys

# ---- config block -------------------------------------------------------------------------
DEFAULT_LOG = pathlib.Path.home() / "AppData/Local/hermes/logs/gateway.log"
DEFAULT_HOURS = 24
RECONNECT_THRESHOLD = 6  # ALERT when reconnects exceed this
# --------------------------------------------------------------------------------------------

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
INBOUND_RE = re.compile(r"gateway\.run: inbound message")

# Fixed patterns, tried in this order; a line counts for the first shape it matches.
SHAPES = (
    ("network_warnings", re.compile(r"WARNING plugins\.platforms\.telegram\.telegram_network:")),
    ("degraded_polls", re.compile(r"Telegram polling degraded")),
    ("degraded_reconnects", re.compile(r"telegram reconnected in degraded mode")),
    ("reconnects", re.compile(r"Telegram network error.*reconnect|Telegram polling reconnect failed")),
    ("connects", re.compile(r"Connected to Telegram \(polling mode\)")),
)


def settings():
    log = pathlib.Path(os.environ.get("HUB_TG_LOG") or DEFAULT_LOG)
    hours = float(os.environ.get("HUB_TG_HOURS") or DEFAULT_HOURS)
    raw_now = os.environ.get("HUB_TG_NOW")
    now = datetime.datetime.strptime(raw_now, TS_FORMAT) if raw_now else datetime.datetime.now()
    return log, hours, now


def count_log(log, hours, now):
    counts = {name: 0 for name, _ in SHAPES}
    cutoff = now - datetime.timedelta(hours=hours)
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if INBOUND_RE.search(line):
                continue
            m = TS_RE.match(line)
            if not m:
                continue
            try:
                ts = datetime.datetime.strptime(m.group(1), TS_FORMAT)
            except ValueError:
                continue
            if ts < cutoff or ts > now:
                continue
            for name, pat in SHAPES:
                if pat.search(line):
                    counts[name] += 1
                    break
    return counts


def main():
    try:
        log, hours, now = settings()
        counts = count_log(log, hours, now)
    except (OSError, ValueError):
        print("VERDICT UNREADABLE")
        return 2
    for name, _ in SHAPES:
        print("%s %d" % (name, counts[name]))
    alert = (counts["degraded_polls"] + counts["degraded_reconnects"] > 0
             or counts["reconnects"] > RECONNECT_THRESHOLD)
    print("VERDICT ALERT" if alert else "VERDICT OK")
    return 1 if alert else 0


if __name__ == "__main__":
    sys.exit(main())
