"""Fixture test for hephaestus/scripts/hub_telegram_watch.py on synthetic log lines.

Prints one row per case, PASS or FAIL, then a total, then rc. The tree under test is the TREE
constant below (a driver may set test_hub_telegram_watch.TREE before main()); it is never an
argument. On a tree with no script every row reads FAIL. Synthetic fixtures only.
"""
import os, pathlib, re, subprocess, sys

HOME = pathlib.Path.home()
REAL_PY = HOME / "AppData/Local/Programs/Python/Python314/python.exe"
SCRATCH = HOME / ".loop/scratch/RELIABLE-01/T15"
TREES = {
    "prefix": HOME / ".loop/scratch/RELIABLE-01/prefix/145746a",
    "fixed": HOME / ".loop/work/RELIABLE-01/kit",
}
TREE = "fixed"
SCRIPT_REL = "hephaestus/scripts/hub_telegram_watch.py"
NOW = "2026-11-19 12:00:00"
MARKER = "zq7marker-lantern"
OUT_RE = re.compile(r"^(?:[a-z_]+ \d+|VERDICT (?:OK|ALERT|UNREADABLE))$")

NET = "WARNING plugins.platforms.telegram.telegram_network: [Telegram] Sticky Telegram path <IP> failed; re-walking IPv4 literals before the hostname"
POLL = "WARNING hermes_plugins.platforms__telegram.adapter: [Telegram] Telegram polling degraded (heartbeat probe); gateway stays alive and will r..."
DEGR = "INFO gateway.run: [warning sign] telegram reconnected in degraded mode (receive path not yet confirmed)"
RECO = "WARNING hermes_plugins.platforms__telegram.adapter: [Telegram] Telegram network error (attempt 1/5), reconnecting in 5s. Error: ConnectError"
CONN = "INFO hermes_plugins.platforms__telegram.adapter: [Telegram] Connected to Telegram (polling mode)"
INBOUND = "INFO gateway.run: inbound message: platform=telegram user=Fixture Person chat=0000 msg=%s Telegram polling degraded"


def sp(text):
    t = str(text)
    for h in (str(HOME), str(HOME).replace("\\", "/")):
        t = t.replace(h, "~")
    return t


def write_log(name, rows):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    p = SCRATCH / name
    p.write_text("\n".join("%s %s" % (ts, body) for ts, body in rows) + "\n", encoding="utf-8")
    return p


def run(log, hours=None):
    script = TREES[TREE] / SCRIPT_REL
    if not script.is_file():
        return None, b""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HUB_TG_LOG=str(log), HUB_TG_NOW=NOW)
    env.pop("HUB_TG_HOURS", None)
    if hours is not None:
        env["HUB_TG_HOURS"] = str(hours)
    p = subprocess.run([str(REAL_PY), str(script)], env=env, capture_output=True)
    return p.returncode, p.stdout + p.stderr


def lines(out):
    return out.decode("utf-8", "replace").splitlines()


def verdict(out):
    for ln in lines(out):
        if ln.startswith("VERDICT "):
            return ln[8:]
    return None


def count(out, shape):
    for ln in lines(out):
        if ln.startswith(shape + " "):
            return int(ln.split()[1])
    return None


def main():
    rows = []
    recent = "2026-11-19 10:00:00"
    old = "2026-11-17 10:00:00"

    p = write_log("quiet.log", [(recent, NET), (recent, NET), (recent, CONN)])
    rc, out = run(p)
    rows.append(("quiet log gives OK, exit 0, counts by shape",
                 rc == 0 and verdict(out) == "OK" and count(out, "network_warnings") == 2 and count(out, "connects") == 1))

    p = write_log("poll.log", [(recent, CONN), (recent, POLL)])
    rc, out = run(p)
    rows.append(("one degraded poll gives ALERT, exit 1",
                 rc == 1 and verdict(out) == "ALERT" and count(out, "degraded_polls") == 1))

    p = write_log("degr.log", [(recent, DEGR)])
    rc, out = run(p)
    rows.append(("one degraded reconnect gives ALERT, exit 1",
                 rc == 1 and verdict(out) == "ALERT" and count(out, "degraded_reconnects") == 1))

    p = write_log("reco7.log", [(recent, RECO)] * 7)
    rc, out = run(p)
    rows.append(("7 reconnects (above threshold 6) give ALERT, exit 1",
                 rc == 1 and verdict(out) == "ALERT" and count(out, "reconnects") == 7))

    p = write_log("reco6.log", [(recent, RECO)] * 6)
    rc, out = run(p)
    rows.append(("6 reconnects (at threshold) give OK, exit 0",
                 rc == 0 and verdict(out) == "OK" and count(out, "reconnects") == 6))

    p = write_log("old.log", [(old, POLL), (old, DEGR), (old, RECO), (recent, CONN)])
    rc, out = run(p)
    rows.append(("lines older than the window are not counted",
                 rc == 0 and verdict(out) == "OK" and count(out, "degraded_polls") == 0
                 and count(out, "reconnects") == 0 and count(out, "connects") == 1))

    rc, out = run(p, hours=72)
    rows.append(("a wider window (HUB_TG_HOURS=72) counts the older lines",
                 rc == 1 and verdict(out) == "ALERT" and count(out, "degraded_polls") == 1))

    rc, out = run(SCRATCH / "no-such-file.log")
    rows.append(("an unreadable path gives exit 2",
                 rc == 2 and verdict(out) == "UNREADABLE"))

    p = write_log("inbound.log", [(recent, INBOUND % MARKER), (recent, CONN)])
    rc, out = run(p)
    rows.append(("planted inbound line: marker absent from output bytes, line not counted",
                 verdict(out) is not None and MARKER.encode() not in out
                 and count(out, "degraded_polls") == 0 and rc == 0))
    rows.append(("output holds only shape-count and verdict lines (no line text)",
                 verdict(out) is not None and all(OUT_RE.match(ln) for ln in lines(out))))

    before = sorted(x.name for x in SCRATCH.iterdir())
    run(p)
    rows.append(("a run writes no file in the fixture folder",
                 verdict(out) is not None and before == sorted(x.name for x in SCRATCH.iterdir())))

    print("tree %s" % TREE)
    fails = 0
    for name, ok in rows:
        print("%s  %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("total %d rows, %d PASS, %d FAIL" % (len(rows), len(rows) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    rc = main()
    print("rc %d" % rc)
    sys.exit(rc)
