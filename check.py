#!/usr/bin/env python3
"""check.py -- check the library: certify, mutate, census.

    python check.py INSTANCE.json         certify only (seconds).
    python check.py INSTANCE.json --deep  certify, then a fresh mutation
                                             run, then (coverage, one
                                             variable) the mutant census.
                                             Minutes per instance.
    python check.py --library             certify every instance in the
                                             library/ folder, controls
                                             included. Fast; run after any
                                             edit.
    python check.py --library DIR         same, for instances in DIR.
    python check.py --all                 legacy: instances in the
                                             current directory.
    Add --deep to any of the above for the full pipeline (fresh
    mutation run and mutant census). Slow; a pre-release job, not a
    routine one.

mutate.py and mutant_census.py are also standalone tools; this script
only orchestrates them. See README, "Command reference", for when to
run them directly.

The engine scripts (certify.py, mutate.py, mutant_census.py) are located
relative to this file, so the workflow can be invoked from any working
directory. Mutation and census TSVs are written next to their instance.

An instance whose "name" field begins with "CONTROL" is expected to FAIL
certification and is reported OK only when the engine actually ran and
mismatched. Everything else is expected to pass. A lint pass runs first
and catches structural problems before they masquerade as certification
verdicts. Committed TSVs are checked for staleness against the mutant
count implied by the instance. Exit status 0 iff every instance behaves
as expected and no TSV is stale.
"""
import json, os, subprocess, sys, glob

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
def tool(name): return os.path.join(HERE, name)

def run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or HERE)

# ---------------- lint ----------------

def lint(path):
    """Structural checks that should fail loudly before certification."""
    problems, warnings = [], []
    try:
        d = json.load(open(path))
    except Exception as e:
        return [f"unparseable JSON: {e}"], [], None
    mode = d.get("mode")
    if mode is None:
        # older instances omit the field; certify.py infers it, so infer the same way
        mode = "coverage" if "expected_coverage" in d else ("level" if ("expected_profile" in d or "expected_level" in d) else None)
    if mode not in ("coverage", "level"):
        problems.append("mode is absent and not inferable from expected_coverage/expected_profile")
    for key in ("variables", "parameters", "objective", "pieces", "slices"):
        if key not in d:
            problems.append(f"missing field {key!r}")
    if mode == "coverage" and "expected_coverage" not in d:
        problems.append("coverage instance without expected_coverage")
    if mode == "level" and "expected_profile" not in d and "expected_level" not in d:
        problems.append("level instance without expected_profile/expected_level")
    sl = d.get("slices", [])
    if len(set(sl)) != len(sl):
        problems.append("duplicate slices")
    if mode == "coverage" and "expected_coverage" in d and not d.get("name", "").startswith("CONTROL"):
        thr = d["expected_coverage"].get("threshold")
        if thr not in sl:
            warnings.append(f"threshold {thr} is not itself a slice; the facet witness at equality goes unchecked")
        name = d.get("name", "")
        if "/" in name and thr and thr not in name:
            warnings.append(f"name states a fraction but not the declared threshold {thr}; names should be checked claims")
    for tname, t in d.get("tools", {}).items():
        if not t.get("fail_options") and mode == "coverage":
            warnings.append(f"tool {tname} has no fail options (never fails; is it a tool or a region row?)")
    return problems, warnings, d

def mutant_count(d):
    n = 0
    for t in d.get("tools", {}).values():
        for opt in t.get("fail_options", []):
            for atom in opt:
                n += 2 * len(atom[1])
    for p in d.get("pieces", {}).values():
        for con in p.get("region", []):
            n += 2 * len(con[1])
    return n

def tsv_stale(path, d):
    tsv = path.replace(".json", ".mutation.tsv")
    if not os.path.exists(tsv):
        return None   # absent is not stale; --deep creates it
    rows = sum(1 for l in open(tsv) if "\t" in l and not l.startswith("mutant\t"))
    want = mutant_count(d)
    if rows != want:
        return f"mutation TSV stale: {rows} rows, instance implies {want} mutants (rerun --deep)"
    return None

# ---------------- per-instance ----------------

def censusable(d):
    return d.get("mode") == "coverage" and len(d.get("variables", [])) == 1

def one(path, do_mutate=False):
    problems, warnings, d = lint(path)
    if problems:
        return "LINT FAILED: " + "; ".join(problems), False, ""
    note = ("  [lint: " + "; ".join(warnings) + "]") if warnings else ""
    ctrl = d.get("name", "").startswith("CONTROL")
    r = run([PY, tool("certify.py"), os.path.abspath(path)])
    passed = (r.returncode == 0)
    if ctrl:
        if not passed and not r.stdout.strip():
            return "ENGINE DID NOT RUN (control verdict meaningless)", False, ""
        status = "OK (control failed as required)" if not passed else "BROKEN CONTROL: it passed"
        return status + note, not passed, ""
    if not passed:
        if not r.stdout.strip():
            err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "no output"
            return f"ENGINE DID NOT RUN ({err})", False, ""
        tail = "\n".join(r.stdout.strip().splitlines()[-6:])
        return "CERTIFY FAILED" + note, False, tail
    detail = r.stdout.strip().splitlines()[-1]
    stale = tsv_stale(path, d)
    if stale and not do_mutate:
        return detail + note + "  !! " + stale, False, ""
    if do_mutate:
        tsv = path.replace(".json", ".mutation.tsv")
        if os.path.exists(tsv):
            os.unlink(tsv)
        m = run([PY, tool("mutate.py"), os.path.abspath(path)])
        last = m.stdout.strip().splitlines()[-1] if m.stdout.strip() else "mutate: no output"
        detail += " | " + last.replace("batch 1/1: ", "")
        if censusable(d):
            c = run([PY, tool("mutant_census.py"), os.path.abspath(path)])
            cl = [l for l in c.stdout.strip().splitlines() if ".json" in l]
            if cl:
                detail += " | census: " + cl[-1].split(": ", 1)[-1]
                if "BRACKETABLE" in cl[-1]:
                    detail += "  <-- add a slice in the reported interval and rerun"
    return detail + note, True, ""

# ---------------- main ----------------

def main():
    argv = sys.argv[1:]
    deep = "--deep" in argv
    argv = [a for a in argv if a != "--deep"]

    if argv and argv[0] == "--library":
        d = argv[1] if len(argv) > 1 else os.path.join(HERE, "library")
        files = sorted(glob.glob(os.path.join(d, "*.json")))
        if not files:
            sys.exit(f"no instances found in {d}")
    elif argv and argv[0] == "--all":
        files = sorted(glob.glob("*.json"))
    elif len(argv) == 1:
        status, ok, err = one(argv[0], do_mutate=deep)
        print(f"{argv[0]}: {status}")
        if err:
            print(err)
        sys.exit(0 if ok else 1)
    else:
        sys.exit(__doc__)

    allok, n_pass, n_ctrl = True, 0, 0
    for p in files:
        status, ok, err = one(p, do_mutate=deep)
        mark = "  " if ok else "!!"
        print(f"{mark} {os.path.basename(p):<36} {status}")
        if err:
            print("     " + err.replace("\n", "\n     "))
        allok = allok and ok
        if ok:
            n_ctrl += status.startswith("OK (control")
            n_pass += not status.startswith("OK (control")
    print()
    print(f"{n_pass} certified, {n_ctrl} controls behaving. "
          + ("LIBRARY CONSISTENT." if allok else "LIBRARY INCONSISTENT: see !! lines."))
    sys.exit(0 if allok else 1)

if __name__ == "__main__":
    main()
