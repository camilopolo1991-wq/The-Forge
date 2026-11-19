"""Fixture test for the hermes-python shim (both forms) and loop_autoresume.py's PY.

Prints one row per case, PASS or FAIL, then a total, then rc. The tree under test is the TREE
constant below (a driver may set test_hermes_python_shim.TREE before main()); it is never an argument.
On a tree with no shim the shim rows read FAIL.
"""
import os, pathlib, shutil, subprocess, sys

HOME = pathlib.Path.home()
REAL_PY = HOME / "AppData/Local/Programs/Python/Python314/python.exe"
SCRATCH = HOME / ".loop/scratch/RELIABLE-01/T07"
TREES = {
    "prefix": HOME / ".loop/scratch/RELIABLE-01/prefix/145746a",
    "fixed": HOME / ".loop/work/RELIABLE-01/kit",
}
TREE = "fixed"
OLD, NEW = "python-3.14.7+20260901-win32-x64", "python-3.14.10+20261101-win32-x64"


def sp(text):
    t = str(text)
    for h in (str(HOME), str(HOME).replace("\\", "/")):
        t = t.replace(h, "~")
    return t


def norm(p):
    return os.path.normcase(os.path.normpath(str(p).strip()))


def bash():
    cand = pathlib.Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    return str(cand) if cand.is_file() else (shutil.which("bash") or "bash")


def build_fixture():
    fx = SCRATCH / "fixture"
    if fx.exists():
        shutil.rmtree(fx)
    for name in (OLD, NEW):
        d = fx / "full/hermes/tools" / name
        d.mkdir(parents=True)
        shutil.copy2(REAL_PY, d / "python.exe")
        for dll in REAL_PY.parent.glob("*.dll"):
            shutil.copy2(dll, d / dll.name)
    (fx / "empty/hermes/tools").mkdir(parents=True)
    return fx


def child_env(local_app_data, hermes_py=None):
    env = dict(os.environ)
    env.pop("HERMES_PY", None)
    env["LOCALAPPDATA"] = str(local_app_data)
    env["PYTHONHOME"] = str(REAL_PY.parent)  # lets the copied interpreters find the standard library
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if hermes_py:
        env["HERMES_PY"] = str(hermes_py)
    return env


def call(form, shim, args, env):
    cmd = [bash(), str(shim)] + args if form == "sh" else [str(shim)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:  # shim absent or not runnable
        return None, "", "%s" % type(e).__name__


def shim_rows(tree, fx):
    rows = []
    full, empty = fx / "full", fx / "empty"
    want_new = full / "hermes/tools" / NEW / "python.exe"
    want_old = full / "hermes/tools" / OLD / "python.exe"
    for form, fname in (("sh", "hephaestus/shims/hermes-python"), ("cmd", "hephaestus/shims/hermes-python.cmd")):
        shim = tree / fname
        present = shim.is_file()
        rc, out, err = call(form, shim, ["--which"], child_env(full))
        ok = present and rc == 0 and norm(out) == norm(want_new)
        rows.append((ok, "%s --which picks 3.14.10 over 3.14.7" % form, "present=%s rc=%s out=%s" % (present, rc, sp(out.strip()))))
        rc, out, err = call(form, shim, ["--which"], child_env(full, want_old))
        ok = present and rc == 0 and norm(out) == norm(want_old)
        rows.append((ok, "%s --which with HERMES_PY set picks it" % form, "rc=%s out=%s" % (rc, sp(out.strip()))))
        rc, out, err = call(form, shim, ["--which"], child_env(empty))
        ok = present and rc == 3 and err.strip() == "hermes-python: no interpreter found" and out.strip() == ""
        rows.append((ok, "%s empty tools folder exits 3 with one stderr line" % form, "rc=%s err=%s" % (rc, sp(err.strip()))))
        rc, out, err = call(form, shim, ["-c", "raise SystemExit(7)"], child_env(full))
        ok = present and rc == 7
        rows.append((ok, "%s runs the interpreter with -c and returns its rc" % form, "rc=%s" % rc))
    return rows


AR_PROBE = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('loop_autoresume_under_test', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(m)\n"
    "print(m.PY)\n"
)


def autoresume_rows(tree, fx):
    rows = []
    script = tree / "hephaestus/scripts/loop_autoresume.py"
    env = child_env(fx / "full")
    for k, v in (("AR_LOOP", "loop"), ("AR_PROF", "prof"), ("AR_RECORD", "record"),
                 ("AR_CHANGE_LEDGER", "ledger.json"), ("AR_STATE", "state.json")):
        env[k] = str(fx / "ar" / v)
    try:
        r = subprocess.run([sys.executable, "-c", AR_PROBE, str(script)], capture_output=True, text=True, env=env, timeout=60)
        py = r.stdout.strip()
        rc = r.returncode
    except Exception as e:
        py, rc = "", None
    exists = bool(py) and pathlib.Path(py).is_file()
    rows.append((exists, "loop_autoresume PY names an existing file", "rc=%s PY=%s" % (rc, sp(py))))
    newest = exists and norm(py) == norm(fx / "full/hermes/tools" / NEW / "python.exe")
    rows.append((newest, "loop_autoresume PY is the newest fixture interpreter", "PY=%s" % sp(py)))
    return rows


def main():
    tree = TREES[TREE]
    print("cmd: %s %s (tree=%s)" % (sp(sys.executable), sp(sys.argv[0]), TREE))
    print("tree: %s" % sp(tree))
    fx = build_fixture()
    rows = shim_rows(tree, fx) + autoresume_rows(tree, fx)
    for ok, name, detail in rows:
        print("%s | %s | %s" % ("PASS" if ok else "FAIL", name, detail))
    npass = sum(1 for r in rows if r[0])
    print("total: %d PASS, %d FAIL, %d rows" % (npass, len(rows) - npass, len(rows)))
    rc = 0 if npass == len(rows) else 1
    print("rc %d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
