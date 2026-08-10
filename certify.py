#!/usr/bin/env python3
"""
certify.py -- Exact certification of sieve threshold profiles, instance as data.

Generalizes fm_exact.py (companion to "A One-Hypothesis Reduction for
Primes in [4n^2-n, 4n^2+n]", Appendix A). The engine knows nothing about
any particular sieve problem; a problem INSTANCE is a JSON file declaring:

  variables    block coordinates x (any dimension), one of which is the
               OBJECTIVE (the level exponent to be minimized);
  parameters   slice parameters (e.g. gamma); every constraint is linear
               in the variables with right-hand side affine in the
               parameters, all coefficients rational (given as strings);
  tools        each tool is a list of FAIL OPTIONS; a fail option is a
               conjunction of constraints (negated pass conditions).
               A tool fails at x iff some fail option holds at x;
  pieces       each piece type has a region (rational-linear box) and a
               list of applicable tools;
  slices       parameter values at which to certify;
  expected_profile   optional affine-in-parameters closed form to check;
  ablations    optional named tool-subset removals to test invariance.

CERTIFIED STATEMENT. For each slice and piece, the engine enumerates every
combination of one fail option per tool (distributing the disjunctions),
forms the polytope {fail atoms} + {region}, and computes the exact minimum
of the objective over each nonempty polytope by exhaustive vertex
enumeration: all size-n subsets of the constraint rows, solved over Q by
Gaussian elimination (fractions.Fraction throughout; no floating point).
The profile zeta(slice) is the minimum over polytopes and pieces -- the
first level at which a total-failure witness exists. Closed inequalities
throughout: the reported zeta is the infimum of failing levels, and the
witness sits on the facet (cf. the constraint inventory, Convention 2.3).

WHAT IS NOT CERTIFIED. Soundness of the ENCODING (that each fail option
really is the negation of the tool's true admissibility condition, or a
documented relaxation thereof closed by a hand-proved coverage lemma) is
the instance author's obligation -- see the sandwich pattern in the
constraint inventory, Section 7. The engine certifies the arithmetic of
the reachable set, exactly; it cannot certify the reach of mathematics.

Usage:
  python3 certify.py INSTANCE.json [--witness SLICE] [--no-ablations]

Exit status 0 iff every slice matches expected_profile (when provided).
"""

import argparse
import json
import sys
from fractions import Fraction as F
from itertools import combinations, product


# ------------------------------------------------------------ exact algebra

def solve_square(rows, n):
    """Solve n x n system rows (each: coeff list + rhs) over Q.
    Returns tuple of Fractions, or None if singular."""
    M = [list(r[0]) + [r[1]] for r in rows]
    for col in range(n):
        piv = next((r for r in range(col, n) if M[r][col] != 0), None)
        if piv is None:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return tuple(M[i][n] for i in range(n))


def min_objective(polytope, n, obj_idx):
    """Exact min of x[obj_idx] over {x : coeffs.x <= rhs} by vertex
    enumeration. Returns (value, point, active_rows) or None if empty.
    Assumes the region bounds the objective below (e.g. a search box)."""
    best = None
    for trip in combinations(range(len(polytope)), n):
        sol = solve_square([polytope[i] for i in trip], n)
        if sol is None:
            continue
        if all(sum(c * x for c, x in zip(row[0], sol)) <= row[1]
               for row in polytope):
            if best is None or sol[obj_idx] < best[0]:
                best = (sol[obj_idx], sol, trip)
    return best


# ------------------------------------------------------------ instance I/O

def frac(s):
    return F(str(s))


class Instance:
    def __init__(self, spec):
        self.spec = spec
        self.name = spec.get("name", "unnamed instance")
        self.variables = spec["variables"]
        self.parameters = spec["parameters"]
        self.n = len(self.variables)
        self.obj_idx = self.variables.index(spec["objective"])
        self.tools = {t: [[self._con(c) for c in option]
                          for option in tool["fail_options"]]
                      for t, tool in spec["tools"].items()}
        self.pieces = {p: {"region": [self._con(c) for c in pc["region"]],
                           "tools": pc["tools"]}
                       for p, pc in spec["pieces"].items()}
        self.slices = [tuple(frac(v) for v in
                             (s if isinstance(s, list) else [s]))
                       for s in spec["slices"]]
        self.expected = spec.get("expected_profile")
        self.ablations = spec.get("ablations", {})

    def _con(self, c):
        coeffs = [frac(v) for v in c[0]]
        rhs = [frac(v) for v in c[1]]           # [const, per-parameter...]
        assert len(coeffs) == self.n and len(rhs) == 1 + len(self.parameters)
        return (coeffs, rhs)

    def rhs_at(self, rhs, slice_vals):
        return rhs[0] + sum(c * v for c, v in zip(rhs[1:], slice_vals))

    def expected_at(self, slice_vals):
        if self.expected is None:
            return None
        e = frac(self.expected.get("const", 0))
        for p, v in zip(self.parameters, slice_vals):
            e += frac(self.expected.get(p, 0)) * v
        if "floor" in self.expected:
            e = max(e, frac(self.expected["floor"]))
        return e


# ------------------------------------------------------------ certification

def certify_piece(inst, piece, slice_vals, removed=()):
    """Exact semantics as before, restructured for speed: materialize the
    deduplicated row universe (region + every fail atom) at this slice,
    solve each candidate vertex (n-subset of rows) exactly once, record
    per vertex which rows it satisfies as a bitmask, then scan fail-option
    combos with integer mask tests only. Vertices are pre-sorted by
    objective, so the first feasible vertex per combo is that combo's
    minimum."""
    pc = inst.pieces[piece]
    active_tools = [t for t in pc["tools"] if t not in removed]
    n = inst.n

    rows, index = [], {}

    def row_id(c, r):
        key = (tuple(c), r)
        if key not in index:
            index[key] = len(rows)
            rows.append((list(c), r))
        return index[key]

    region_mask = 0
    for c, r in pc["region"]:
        region_mask |= 1 << row_id(c, inst.rhs_at(r, slice_vals))

    tool_options = []
    for t in active_tools:
        opts = []
        for option in inst.tools[t]:
            m = 0
            for c, r in option:
                m |= 1 << row_id(c, inst.rhs_at(r, slice_vals))
            opts.append((m, option))
        tool_options.append(opts)

    if len(rows) < n:
        return None

    verts = []
    for sub in combinations(range(len(rows)), n):
        sol = solve_square([rows[i] for i in sub], n)
        if sol is None:
            continue
        sat = 0
        for i, (c, r) in enumerate(rows):
            if sum(a * x for a, x in zip(c, sol)) <= r:
                sat |= 1 << i
        dmask = 0
        for i in sub:
            dmask |= 1 << i
        verts.append((sol[inst.obj_idx], sol, sub, dmask, sat))
    verts.sort(key=lambda v: v[0])

    best = None
    for combo in product(*tool_options):
        mask = region_mask
        for m, _ in combo:
            mask |= m
        for val, sol, sub, dmask, sat in verts:
            if dmask & ~mask or mask & ~sat:
                continue
            if best is None or val < best[0]:
                best = (val, sol, sub,
                        {t: pc["tools"].index(t) for t in active_tools},
                        tuple(o for _, o in combo))
            break
    return best


_slice_cache = {}


def certify_slice(inst, slice_vals, removed=()):
    key = (id(inst), slice_vals, tuple(sorted(removed)))
    if key in _slice_cache:
        return _slice_cache[key]
    results = {}
    for piece in inst.pieces:
        results[piece] = certify_piece(inst, piece, slice_vals, removed)
    vals = [(r[0], p) for p, r in results.items() if r is not None]
    if not vals:
        out = (None, None, results)
    else:
        zmin, pmin = min(vals)
        out = (zmin, pmin, results)
    _slice_cache[key] = out
    return out


def run_coverage(inst, args):
    """Coverage mode: for each slice, report whether a total-failure witness
    exists in any piece (all tools fail simultaneously at some point of the
    region). The certified object is the existence threshold in the slice
    parameter, checked against expected_coverage = {threshold, witness_iff}.
    With witness_iff = "le" and closed inequalities, a witness must exist
    exactly for slice values <= threshold (at equality the witness set is
    the facet itself)."""
    ec = inst.spec.get("expected_coverage")
    base_thr = frac(ec["threshold"]) if ec else None
    state = {"ok": True, "checks": 0, "fails": 0}

    def report(removed=(), expect_thr=None, label="base toolkit"):
        print(f"\ncoverage witnesses ({label}):")
        for sv in inst.slices:
            _, _, per = certify_slice(inst, sv, removed)
            found = {p: r for p, r in per.items() if r is not None}
            exists = bool(found)
            detail = "; ".join(
                f"{p}: {inst.variables[inst.obj_idx]} = {r[1][inst.obj_idx]}"
                for p, r in found.items()) or "-"
            tag = ""
            if expect_thr is not None:
                want = sv[0] <= expect_thr
                match = exists == want
                state["checks"] += 1
                state["fails"] += 0 if match else 1
                state["ok"] = state["ok"] and match
                tag = (f"   [{'OK' if match else 'MISMATCH'}: expected "
                       f"{'witness' if want else 'covered'}]")
            sl = ", ".join(f"{p}={v}" for p, v in zip(inst.parameters, sv))
            print(f"  {sl}:  "
                  f"{'FAILURE WITNESS' if exists else 'covered':>15}  "
                  f"({detail}){tag}")
        if expect_thr is not None:
            print(f"  => checked against threshold {expect_thr} "
                  f"(witness iff slice <= threshold)")

    report(expect_thr=base_thr)
    if inst.ablations and not args.no_ablations:
        for name, ab in inst.ablations.items():
            et = (frac(ab["expected_threshold"])
                  if "expected_threshold" in ab else None)
            report(tuple(ab["remove_tools"]), et,
                   f"ablation '{name}': remove {ab['remove_tools']}")
    print()
    if state["checks"] == 0:
        print("NO EXPECTED VALUES DECLARED -- nothing certified "
              "(add expected_coverage to make this a certificate)")
    elif state["ok"]:
        print(f"CERTIFICATE PASSED -- {state['checks']}/{state['checks']} "
              f"checks match the declared thresholds exactly")
    else:
        print(f"CERTIFICATE FAILED -- {state['fails']} of "
              f"{state['checks']} checks mismatch (see MISMATCH lines)")
    sys.exit(0 if state["ok"] else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instance")
    ap.add_argument("--witness", default=None,
                    help="slice value (comma-separated if multiparameter) "
                         "at which to print the minimizing witness")
    ap.add_argument("--no-ablations", action="store_true")
    args = ap.parse_args()

    with open(args.instance) as f:
        inst = Instance(json.load(f))

    print(f"instance: {inst.name}")
    print(f"variables: {inst.variables}  objective: "
          f"{inst.variables[inst.obj_idx]}  parameters: {inst.parameters}")
    if inst.spec.get("mode") == "coverage":
        run_coverage(inst, args)
    ok = True
    checks = fails = 0

    print("\nprofile:")
    for sv in inst.slices:
        z, piece, per = certify_slice(inst, sv)
        exp = inst.expected_at(sv)
        tag = ""
        if exp is not None:
            match = (z == exp)
            checks += 1
            fails += 0 if match else 1
            ok = ok and match
            tag = f"   expected {exp}  [{'OK' if match else 'MISMATCH'}]"
        pieces_str = ", ".join(
            f"{p}: {r[0] if r else 'no witness in box'}"
            for p, r in per.items())
        sl = ", ".join(f"{p}={v}" for p, v in zip(inst.parameters, sv))
        print(f"  {sl}:  zeta = {z}  ({pieces_str}){tag}")

    if args.witness is not None:
        sv = tuple(frac(v) for v in args.witness.split(","))
        z, piece, per = certify_slice(inst, sv)
        val, point, trip, tool_idx, combo = per[piece]
        print(f"\nwitness at {dict(zip(inst.parameters, sv))} "
              f"(piece {piece}, zeta = {z}):")
        for name, v in zip(inst.variables, point):
            print(f"  {name} = {v}")
        print("  binding fail atoms (one option per tool):")
        for tname, option in zip(
                [t for t in inst.pieces[piece]['tools']
                 if t in tool_idx], combo):
            terms = [f"{c}*{v}" for c, v in
                     zip(option[0][0], inst.variables) if c != 0]
            print(f"    {tname}: {' + '.join(terms)} <= "
                  f"{inst.rhs_at(option[0][1], sv)}"
                  f"{'  (+ conjuncts)' if len(option) > 1 else ''}")

    if inst.ablations and not args.no_ablations:
        print("\nablations (tool removals; zeta can only decrease):")
        for name, ab in inst.ablations.items():
            removed = tuple(ab["remove_tools"])
            changed = []
            for sv in inst.slices:
                z0, _, _ = certify_slice(inst, sv)
                z1, _, _ = certify_slice(inst, sv, removed)
                if z0 != z1:
                    changed.append((sv, z0, z1))
            verdict = ("profile UNCHANGED -- these tools are not needed "
                       "for the optimum" if not changed
                       else f"profile CHANGES at {changed}")
            print(f"  {name} (remove {list(removed)}): {verdict}")

    print()
    if checks == 0:
        print("NO EXPECTED VALUES DECLARED -- nothing certified "
              "(add expected_profile to make this a certificate)")
    elif ok:
        print(f"CERTIFICATE PASSED -- {checks}/{checks} slices match "
              f"the declared profile exactly")
    else:
        print(f"CERTIFICATE FAILED -- {fails} of {checks} slices "
              f"mismatch (see MISMATCH lines)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
