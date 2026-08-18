#!/usr/bin/env python3
"""
mutate.py -- mutation testing for exponent certificates.

Purpose: measure the sensitivity of an instance's acceptance test. Each
mutant perturbs exactly one rational right-hand-side entry (in a fail
atom or a region row) by +/- 1/50 and reruns the certifier. A KILLED
mutant (certificate fails) shows the checks detect that perturbation. A
SURVIVING mutant identifies an entry that is slack at every tested
slice and ablation, which is itself information: the surviving set maps
the non-load-bearing coefficients of the transcription at the declared
slices.

The baseline run must pass, or nothing is measured. 

Usage: python3 mutate.py INSTANCE.json [--chunk k/n]
  --chunk 1/2 runs the first half of the mutant list (for time-limited
  environments); results append to INSTANCE.mutation.tsv.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from fractions import Fraction

EPS = (Fraction(1, 50), Fraction(-1, 50))


def passes(path):
    r = subprocess.run([sys.executable, "certify.py", path],
                       capture_output=True, text=True)
    return r.returncode == 0


def mutants(spec):
    for tname, tool in spec["tools"].items():
        for oi, option in enumerate(tool["fail_options"]):
            for ai, atom in enumerate(option):
                for ri, val in enumerate(atom[1]):
                    for eps in EPS:
                        m = copy.deepcopy(spec)
                        m["tools"][tname]["fail_options"][oi][ai][1][ri] = \
                            str(Fraction(str(val)) + eps)
                        yield (f"tool:{tname}/opt{oi}/atom{ai}/rhs{ri}"
                               f"{'+' if eps > 0 else '-'}", m)
    for pname, piece in spec["pieces"].items():
        for ci, con in enumerate(piece["region"]):
            for ri, val in enumerate(con[1]):
                for eps in EPS:
                    m = copy.deepcopy(spec)
                    m["pieces"][pname]["region"][ci][1][ri] = \
                        str(Fraction(str(val)) + eps)
                    yield (f"region:{pname}/row{ci}/rhs{ri}"
                           f"{'+' if eps > 0 else '-'}", m)


def main():
    instance = sys.argv[1]
    chunk = (1, 1)
    if len(sys.argv) > 3 and sys.argv[2] == "--chunk":
        a, b = sys.argv[3].split("/")
        chunk = (int(a), int(b))

    spec = json.load(open(instance))
    if not passes(instance):
        sys.exit("baseline does not pass; fix the instance first")

    all_m = list(mutants(spec))
    lo = (chunk[0] - 1) * len(all_m) // chunk[1]
    hi = chunk[0] * len(all_m) // chunk[1]
    batch = all_m[lo:hi]
    out = instance.replace(".json", ".mutation.tsv")

    killed = survived = 0
    with open(out, "a") as f:
        for label, m in batch:
            with tempfile.NamedTemporaryFile(
                    "w", suffix=".json", delete=False) as t:
                json.dump(m, t)
                tpath = t.name
            ok = passes(tpath)
            os.unlink(tpath)
            verdict = "SURVIVED" if ok else "killed"
            if ok:
                survived += 1
            else:
                killed += 1
            f.write(f"{label}\t{verdict}\n")
            print(f"{verdict:>8}  {label}")
    print(f"\nbatch {chunk[0]}/{chunk[1]}: {killed} killed, "
          f"{survived} survived, of {len(batch)} mutants "
          f"(full set: {len(all_m)})")


if __name__ == "__main__":
    main()
