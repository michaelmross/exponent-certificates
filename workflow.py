#!/usr/bin/env python3
"""workflow.py -- run the full certification workflow.

    python3 workflow.py INSTANCE.json         certify only (seconds).
    python3 workflow.py INSTANCE.json --deep  certify, then a fresh mutation
                                              run, then (coverage, one
                                              variable) the mutant census.
                                              Minutes per instance.
    python3 workflow.py --all                 certify the whole library,
                                              controls included. Fast; run
                                              after any edit.
    python3 workflow.py --all --deep          the full pipeline on every
                                              instance. Slow; run before
                                              a release or after changing
                                              mutate.py or slices.

An instance whose "name" field begins with "CONTROL" is expected to FAIL
certification, and the workflow reports it as OK only when it does fail.
Everything else is expected to pass. Exit status 0 iff every instance
behaves as expected.

The mutation and census steps rewrite INSTANCE.mutation.tsv and
INSTANCE.census.tsv from scratch, so committed TSVs always match the
committed instance. If the census reports any BRACKETABLE survivor, the
workflow flags it: the fix is to add a slice inside the reported interval
(see README, step 4) and rerun.
"""
import json, os, subprocess, sys, glob

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def is_control(path):
    try:
        return json.load(open(path)).get("name", "").startswith("CONTROL")
    except Exception:
        return False

def censusable(path):
    d = json.load(open(path))
    return d.get("mode") == "coverage" and len(d.get("variables", [])) == 1

def one(path, do_mutate=False):
    ctrl = is_control(path)
    r = run(["python3", "certify.py", path])
    passed = (r.returncode == 0)
    if ctrl:
        status = "OK (control failed as required)" if not passed else "BROKEN CONTROL: it passed"
        return status, not passed, ""
    if not passed:
        tail = "\n".join(r.stdout.strip().splitlines()[-6:])
        return "CERTIFY FAILED", False, tail
    detail = r.stdout.strip().splitlines()[-1]
    extra = ""
    if do_mutate:
        tsv = path.replace(".json", ".mutation.tsv")
        if os.path.exists(tsv):
            os.unlink(tsv)
        m = run(["python3", "mutate.py", path])
        last = m.stdout.strip().splitlines()[-1] if m.stdout.strip() else "mutate: no output"
        extra = " | " + last.replace("batch 1/1: ", "")
        if censusable(path):
            c = run(["python3", "mutant_census.py", path])
            cl = c.stdout.strip().splitlines()
            summary = next((l for l in cl if l.startswith(path)), "")
            extra += " | census: " + summary.split(": ", 1)[-1] if summary else ""
            if "BRACKETABLE" in summary:
                extra += "  <-- add a slice in the reported interval and rerun"
    return detail + extra, True, ""

def main():
    deep = "--deep" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--deep"]
    if len(args) == 1 and args[0] != "--all":
        status, ok, err = one(args[0], do_mutate=deep)
        print(f"{sys.argv[1]}: {status}")
        if err:
            print(err)
        sys.exit(0 if ok else 1)
    allok = True
    files = sorted(glob.glob("*.json"))
    for p in files:
        status, ok, err = one(p, do_mutate=deep)
        mark = "  " if ok else "!!"
        print(f"{mark} {p:<36} {status}")
        if err:
            print("     " + err.replace("\n", "\n     "))
        allok = allok and ok
    print()
    print("LIBRARY " + ("CONSISTENT: every instance behaves as declared."
                        if allok else "INCONSISTENT: see !! lines above."))
    sys.exit(0 if allok else 1)

if __name__ == "__main__":
    main()
