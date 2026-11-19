"""B-19: the launcher and loop-py strip one pair of matching surrounding quotes from LOOP_PY.

Builds a fixture under <loop home>/scratch/RELIABLE-01/T04/: fixture loop homes whose config file sets LOOP_PY to the
running interpreter wrapped in double quotes, in single quotes, and bare, or with LOOP_PY set in the environment the
same three ways. Two kinds of subject run against it:
  launcher  a copy of the launcher under test named loop-echo, beside a module loop_echo.py that prints a fixed marker
  loop-py   bin/loop-py from the same tree, run on a marker script under the fixture home's scratch/ folder; the marker
            only prints if the interpreter it resolved really ran the script
Prints one row per case: kind, case, rc, marker seen, PASS or FAIL. Case rows must run (rc 0, marker seen). Control rows
(mismatched quotes, nested pairs where only one pair is stripped) are expected to fail on both trees (rc 3, no marker)
and are counted apart from the case rows. Then the totals.

The launcher under test is a constant here, never an argument; loop-py is its sibling in the same bin/.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER_UNDER_TEST = os.path.join(os.path.dirname(HERE), "bin", "loop-scan")
FIXTURE = os.path.join(os.path.expanduser("~"), ".loop", "scratch", "RELIABLE-01", "T04")
MARKER = "LOOP_ECHO_MARKER_7f3a"
PYMARKER = "LOOP_PY_MARKER_2c91"


def _bash():
    for p in ("C:/Program Files/Git/bin/bash.exe", "C:/Program Files/Git/usr/bin/bash.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("bash") or "bash"


def _fwd(p):
    return p.replace("\\", "/")


def run_cases(launcher):
    py = _fwd(sys.executable)
    loop_py = os.path.join(os.path.dirname(launcher), "loop-py")
    shutil.rmtree(FIXTURE, ignore_errors=True)
    fbin = os.path.join(FIXTURE, "bin")
    os.makedirs(fbin)
    with open(launcher, "rb") as f:
        text = f.read()
    with open(os.path.join(fbin, "loop-echo"), "wb") as f:
        f.write(text)
    with open(os.path.join(fbin, "loop_echo.py"), "w", newline="\n") as f:
        f.write("print(%r)\n" % MARKER)

    # (case, config value or None, environment value or None, is a case row that must run)
    cases = [
        ("config double quotes", '"%s"' % py, None, True),
        ("config single quotes", "'%s'" % py, None, True),
        ("config unquoted", py, None, True),
        ("env double quotes", None, '"%s"' % py, True),
        ("env single quotes", None, "'%s'" % py, True),
        ("env unquoted", None, py, True),
        ("config mismatched quotes", '"%s\'' % py, None, False),
        ("config nested pairs, only one stripped", "\"'%s'\"" % py, None, False),
    ]
    rows = []
    for kind in ("launcher", "loop-py"):
        for i, (name, cfg, envv, runs) in enumerate(cases):
            home = os.path.join(FIXTURE, "home%d_%s" % (i, "echo" if kind == "launcher" else "py"))
            os.makedirs(os.path.join(home, "scratch"))
            if cfg is not None:
                with open(os.path.join(home, "config.env"), "w", newline="\n") as f:
                    f.write("LOOP_PY=%s\n" % cfg)
            env = dict(os.environ)
            env.pop("LOOP_PY", None)
            env["LOOP_HOME"] = _fwd(home)
            if envv is not None:
                env["LOOP_PY"] = envv
            if kind == "launcher":
                argv = [_bash(), _fwd(os.path.join(fbin, "loop-echo"))]
                marker = MARKER
            else:
                script = os.path.join(home, "scratch", "marker.py")
                with open(script, "w", newline="\n") as f:
                    f.write("print(%r)\n" % PYMARKER)
                argv = [_bash(), _fwd(loop_py), _fwd(script)]
                marker = PYMARKER
            r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
            seen = marker in r.stdout
            ok = (r.returncode == 0 and seen) if runs else (r.returncode == 3 and not seen)
            rows.append((kind, name, r.returncode, seen, ok, not runs))
    return rows


def report(rows):
    for kind, name, rc, seen, ok, ctl in rows:
        print("%-8s %-7s %-42s rc=%-3s marker_seen=%-5s %s" % (
            kind, "CONTROL" if ctl else "CASE", name, rc, seen, "PASS" if ok else "FAIL"))
    cs = [r for r in rows if not r[5]]
    ct = [r for r in rows if r[5]]
    for label, sel in (("launcher", [r for r in cs if r[0] == "launcher"]), ("loop-py", [r for r in cs if r[0] == "loop-py"])):
        print("total %s case rows: %d, %d PASS, %d FAIL" % (label, len(sel), sum(1 for r in sel if r[4]), sum(1 for r in sel if not r[4])))
    print("total case rows: %d, %d PASS, %d FAIL" % (len(cs), sum(1 for r in cs if r[4]), sum(1 for r in cs if not r[4])))
    print("total control rows (expected to fail on both trees): %d, %d held (rc 3, no marker), %d broken" % (
        len(ct), sum(1 for r in ct if r[4]), sum(1 for r in ct if not r[4])))
    return all(r[4] for r in rows)


def test_launcher_interp_quotes():
    assert report(run_cases(LAUNCHER_UNDER_TEST))


if __name__ == "__main__":
    print("launcher under test:", LAUNCHER_UNDER_TEST.replace(os.path.expanduser("~"), "~"))
    sys.exit(0 if report(run_cases(LAUNCHER_UNDER_TEST)) else 1)
