#!/usr/bin/env python3
"""Fixture test for hephaestus/scripts/seat_pacing_check.py (RELIABLE-01 R04).

Synthetic logs only, built under the goal's scratch folder from the masked
line shapes, with fixed timestamps relative to SEAT_PACING_NOW. One row per
case, PASS or FAIL, then a total. The trees under test are constants below;
no command-line argument selects one. SEAT_PACING_TREE=prefix|fixed (the
evidence runners set it) narrows the run to one tree; unset runs both.
Exit 0 when every row is PASS, else 1.
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
TREES = {
    "prefix": HOME / ".loop" / "scratch" / "RELIABLE-01" / "prefix" / "145746a",
    "fixed": HOME / ".loop" / "work" / "RELIABLE-01" / "kit",
}
SCRIPT_REL = Path("hephaestus") / "scripts" / "seat_pacing_check.py"
FIXTURES = HOME / ".loop" / "scratch" / "RELIABLE-01" / "T11"
NOW = datetime(2026, 11, 19, 12, 0, 0)
MARKER = "PLANTEDMARKERWORD7Q"
SEATS = ("hub", "hades", "hephaestus", "poseidon", "zeus")
LEADER_TEXT = "You've hit your 5-hour limit · resets 3:00pm (America/Bogota)\n"


def tilde(text):
    h = str(HOME)
    return text.replace(h, "~").replace(h.replace("\\", "/"), "~")


def ts(age_h):
    return (NOW - timedelta(hours=age_h)).strftime("%Y-%m-%d %H:%M:%S,000")


def ordinary(age_h):
    return "%s INFO gateway.run: ordinary line" % ts(age_h)


def cap(age_h, extra=""):
    return ("%s ERROR agent.chat_completion_helpers: Streaming failed before delivery: "
            "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', "
            "'message': 'This request would exceed your account limit %s'}}" % (ts(age_h), extra))


def credit(age_h, extra=""):
    return ("%s ERROR agent.chat_completion_helpers: Streaming failed before delivery: "
            "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', "
            "'message': 'Usage credits are required for fast mode. %s'}}" % (ts(age_h), extra))


def delegate(age_h):
    return ("%s WARNING run_agent: Tool delegate_task returned error (9s): "
            "Anthropic rate-limited every one of 3 attempts" % ts(age_h))


def seat_path(home, seat):
    if seat == "hub":
        return home / "logs" / "agent.log"
    return home / "profiles" / seat / "logs" / "agent.log"


def build(case, seat_lines=None, absent=(), dir_logs=(), leader_files=()):
    root = FIXTURES / case
    shutil.rmtree(root, ignore_errors=True)
    home, dispatch = root / "home", root / "dispatch"
    seat_lines = seat_lines or {}
    for seat in SEATS:
        p = seat_path(home, seat)
        if seat in absent:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if seat in dir_logs:
            p.mkdir()
            continue
        lines = [ordinary(1), ordinary(2)] + seat_lines.get(seat, [])
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dispatch.mkdir(parents=True, exist_ok=True)
    files = [("ordinary.log", "ordinary run log line\n", 1)] + list(leader_files)
    for name, text, age_h in files:
        f = dispatch / name
        f.write_text(text, encoding="utf-8")
        t = (NOW - timedelta(hours=age_h)).timestamp()
        os.utime(f, (t, t))
    return home, dispatch


def run_script(tree, home, dispatch, extra_env=None):
    env = dict(os.environ)
    for k in ("SEAT_PACING_HOURS",):
        env.pop(k, None)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "SEAT_PACING_HOME": str(home),
                "SEAT_PACING_DISPATCH": str(dispatch), "SEAT_PACING_NOW": NOW.isoformat()})
    env.update(extra_env or {})
    p = subprocess.run([sys.executable, str(tree / SCRIPT_REL)], env=env,
                       capture_output=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


ROW_RE = re.compile(r"^seat=(\w+) cap=(\S+) credit=(\S+) verdict=(\w+)$")
TOTAL_RE = re.compile(r"^total rows=(\d+) not_ok=(\d+) ")


def parse(out):
    rows, total = {}, None
    for line in out.decode("utf-8", "replace").splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3), m.group(4))
        m = TOTAL_RE.match(line)
        if m:
            total = (int(m.group(1)), int(m.group(2)))
    return rows, total


def expected(**over):
    exp = {s: ("0", "0", "OK") for s in SEATS}
    exp["leader"] = ("0", "-", "OK")
    exp.update(over)
    return exp


def check_rows(rc, out, exp, exp_rc):
    rows, total = parse(out)
    not_ok = sum(1 for v in exp.values() if v[2] not in ("OK", "ABSENT"))
    ok = rc == exp_rc and rows == exp and total == (len(exp), not_ok)
    return ok, "rc=%s rows=%d" % (rc, len(rows))


def cases():
    """Each case: name, build kwargs, env, expected rows, expected rc, extra(home, out, err)."""
    caps5 = [cap(h) for h in (1, 2, 3, 4, 5)]
    c = []
    c.append(("quiet-all-ok", dict(seat_lines={"hephaestus": [delegate(1)]}), {},
              expected(), 0, None))
    c.append(("one-cap-line-slow", dict(seat_lines={"hephaestus": [cap(1)]}), {},
              expected(hephaestus=("1", "0", "SLOW")), 1, None))
    c.append(("four-cap-lines-slow", dict(seat_lines={"hephaestus": caps5[:4]}), {},
              expected(hephaestus=("4", "0", "SLOW")), 1, None))
    c.append(("five-cap-lines-pause", dict(seat_lines={"hephaestus": caps5}), {},
              expected(hephaestus=("5", "0", "PAUSE")), 1, None))
    c.append(("cap-and-credit-cap-wins", dict(seat_lines={"hephaestus": [cap(1), credit(2), credit(3)]}), {},
              expected(hephaestus=("1", "2", "SLOW")), 1, None))

    def credit_extra(home, out, err):
        # a check that counts the cap class alone reads this seat as OK
        data = seat_path(home, "hades").read_bytes()
        cap_only = len(re.findall(rb"would exceed your account", data))
        return cap_only == 0 and "cap-only-reading=OK"

    c.append(("credit-only-reads-credit", dict(seat_lines={"hades": [credit(h) for h in (1, 2, 3, 4, 5, 6)]}), {},
              expected(hades=("0", "6", "CREDIT")), 1, credit_extra))
    c.append(("old-lines-not-counted", dict(seat_lines={"zeus": [cap(h) for h in (25, 26, 27, 28, 29, 30)],
                                                         "poseidon": [cap(23)]}), {},
              expected(poseidon=("1", "0", "SLOW")), 1, None))
    c.append(("hours-override-widens-window", dict(seat_lines={"zeus": [cap(30)]}),
              {"SEAT_PACING_HOURS": "48"},
              expected(zeus=("1", "0", "SLOW")), 1, None))
    c.append(("leader-limit-line", dict(leader_files=[("hit.log", LEADER_TEXT, 2),
                                                      ("hit-old.log", LEADER_TEXT, 30)]), {},
              expected(leader=("1", "-", "SLOW")), 1, None))
    c.append(("missing-seat-log-absent", dict(absent=("zeus",)), {},
              expected(zeus=("-", "-", "ABSENT")), 0, None))
    c.append(("unreadable-log-exit-2", dict(dir_logs=("poseidon",)), {},
              expected(poseidon=("-", "-", "UNREADABLE")), 2, None))

    def marker_extra(home, out, err):
        planted = seat_path(home, "hades").read_bytes().count(MARKER.encode())
        found = (out + err).count(MARKER.encode())
        return planted >= 1 and found == 0 and "marker planted=%d in-output=%d" % (planted, found)

    c.append(("marker-never-printed",
              dict(seat_lines={"hades": [cap(1, MARKER), cap(2, MARKER), credit(3, MARKER)]}), {},
              expected(hades=("2", "1", "SLOW")), 1, marker_extra))
    return c


def run_tree(label, tree):
    results = []
    present = (tree / SCRIPT_REL).is_file()
    results.append(("script-present", present, "script present=%s" % present))
    for name, kw, env, exp, exp_rc, extra in cases():
        home, dispatch = build("%s-%s" % (label, name), **kw)
        try:
            rc, out, err = run_script(tree, home, dispatch, env)
        except Exception as exc:  # a failure to run is a FAIL row, not a crash
            results.append((name, False, "run error %s" % type(exc).__name__))
            continue
        ok, detail = check_rows(rc, out, exp, exp_rc)
        if extra is not None:
            res = extra(home, out, err)
            ok = ok and bool(res)
            detail += " " + (res if isinstance(res, str) else "extra check failed")
        if not ok and err:
            detail += " stderr-bytes=%d" % len(err)
        results.append((name, ok, detail))
    return results


def main():
    pick = os.environ.get("SEAT_PACING_TREE", "")
    labels = [pick] if pick in TREES else list(TREES)
    npass = nfail = 0
    for label in labels:
        for name, ok, detail in run_tree(label, TREES[label]):
            print("[%s] %s: %s (%s)" % (label, name, "PASS" if ok else "FAIL", detail))
            npass += ok
            nfail += not ok
    print("total pass=%d fail=%d" % (npass, nfail))
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
