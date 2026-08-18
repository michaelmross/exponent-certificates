# certify.py instance schema and transcription protocol

An INSTANCE is a JSON file declaring a sieve/coverage optimization problem
in exact rational arithmetic. The engine (certify.py) is problem-agnostic:
everything problem-specific lives in the instance. The certified
library in `library/` accompanies this spec: twelve instances spanning
both modes, with `jn_tail.json` the level-mode exemplar and
`rs_pns.json` the coverage-mode exemplar, plus two CONTROL instances
(names beginning `CONTROL`) that must FAIL certification and exist to
prove the engine can detect error. Each instance ships with its
committed evidence: the full run report `*.certify.txt`, the mutation
results `*.mutation.tsv`, the survivor classification `*.census.tsv`,
and a hand-written audit note `*_AUDIT.md`.

## 1. File anatomy

```
name        string. Displayed verbatim; state the certified claim in it.
mode        "level" (default) or "coverage". See section 4.
comment     string. REQUIRED in practice: state the source paper, the
            variable/parameter meanings, and every encoding convention
            (see section 5). This is the audit trail.
variables   list of block-coordinate names, any dimension n.
parameters  list of slice-parameter names (the profile runs over these).
objective   one of `variables`. Level mode minimizes it over failure
            polytopes; coverage mode reports it at the witness.
tools       map name -> {provenance, fail_options}. See section 2.
pieces      map name -> {region, tools}. A piece is one branch of the
            decomposition (e.g. type I / type II); its region is the
            rational-linear box of block coordinates it must cover, and
            its tools are the estimates applicable there.
slices      list of parameter values (rationals as strings; a list of
            values when there are several parameters).
expected_profile / expected_coverage   the acceptance test. Section 4.
ablations   map name -> {remove_tools, note, [expected_threshold]}.
            Each ablation re-certifies with a tool subset removed.
```

## 2. Constraints, tools, fail options

A CONSTRAINT is `[[coeffs...], [rhs...]]` meaning

    coeffs . x  <=  rhs[0] + rhs[1]*param_1 + ... + rhs[k]*param_k

with every entry a rational given as a string ("761/143", "-5", "1/3").
`coeffs` has one entry per variable, in declaration order; `rhs` has
1 + (number of parameters) entries. All inequalities are CLOSED.

A TOOL is the negation of an estimate's admissibility condition:

- The estimate PASSES at x iff its (conjunctive) window conditions hold.
- `fail_options` is the negation in disjunctive normal form: a list of
  OPTIONS, each option a list (conjunction) of constraints. The tool
  fails at x iff at least one option holds.
- An estimate valid on `nu <= f(gamma) AND nu <= g(gamma)` therefore
  gets fail_options `[[nu >= f]], [[nu >= g]]` — two single-atom options
  — encoded with the >= flipped into <= form by negating coefficients.

`provenance` must cite the exact statement transcribed (paper, section,
lemma). It is ignored by the engine and required by the audit.

## 3. Semantics (what the engine certifies)

Fix a slice. For each piece, the engine enumerates every combination of
one fail option per applicable tool, forms the polytope

    {region constraints} + {chosen fail atoms},

and, over each nonempty polytope, computes the exact minimum of the
objective by exhaustive vertex enumeration over Q (all n-subsets of
rows, Gaussian elimination in fractions.Fraction, feasibility check
against all rows). A point of such a polytope is a
COVERAGE-GAP WITNESS (engine output: `GAP WITNESS`): a block
configuration where every tool fails simultaneously.

Because inequalities are closed and margins (eta, epsilon, kappa) are
dropped, certified thresholds are attained on facets: at the critical
slice the witness set collapses to the facet itself.

## 4. Modes and acceptance tests

LEVEL mode (default; jn_tail.json): the certified object is
zeta(slice) = min objective over all witnesses — the first level at
which total failure occurs. `expected_profile` gives the closed form as
affine coefficients over the parameters, plus optional `"floor"` for
out-of-domain clamping. The engine exits 0 iff every slice matches
exactly.

COVERAGE mode (rs_pns.json): the certified object is witness EXISTENCE
per slice. `expected_coverage = {threshold, witness_iff: "le"}` asserts
a witness exists iff slice <= threshold. Ablations may carry their own
`expected_threshold`. Exit 0 iff every slice matches under the base
toolkit and every ablation.

In both modes the expected values must come from the SOURCE PAPER, not
from a prior run: the match between transcription and publication is
the point of the exercise.

## 5. Soundness obligations (the sandwich discipline)

The engine certifies the arithmetic of the encoded system exactly. It
does NOT certify that the encoding is faithful to the paper. The
instance author owes, in `comment` and per-tool `provenance`:

1. RELAXATIONS: any tool condition deliberately omitted or weakened,
   with the direction of the resulting bound (omissions make failure
   easier, so certified thresholds are conservative), and the hand
   argument that closes the gap on the relevant region.
2. DESIGN CHOICES: parameters the paper fixes rather than quantifies
   (e.g. alpha = 1-gamma in Rivat-Sargos Section 5). Each forces a
   documented decision, never a silent one. PIN it (a constant, with
   provenance) when freeing it would leave the rational-affine layer
   or change which constraints exist: exponent pairs, the identity
   parameter l, a derivative-test order q. FREE it (a block variable)
   when it enters affinely, so the certificate tests the choice
   instead of inheriting it: this is how dimitrov_squarefree.json
   found the paper's split suboptimal. A contestable pin that cannot
   be freed gets a VARIANT instance at a different pin
   (guo_guo_lu_A7.json), which performs the optimality test the LP
   cannot.
3. EDGE CONVENTIONS: window edges the paper covers by construction
   (eta-shifted endpoints) carry no fail atom; only genuine caps do.
   Say which edges were so treated.
4. SCOPE: what lies outside the linear regime entirely (numerical
   Buchstab integration, zero-density inputs, mean-value theorems).
   The instance must not silently span such a layer; certify the
   linear layer and state the boundary.

## 6. Transcription protocol (human or AI-assisted)

The construction of an instance from a paper is mechanical enough to
delegate — to a careful reader or to an AI under these guidelines —
BECAUSE the acceptance test is self-checking: an unfaithful atom table
has no reason to reproduce the paper's exact published rationals, let
alone several of them simultaneously under ablation.

Step 1. Identify the block coordinates (exponent variables) and slice
        parameter, and the decomposition pieces with their regions.
Step 2. Harvest atoms: every statement of the form "the estimate is
        valid / the term is negligible provided X <= x^{f(param)}"
        with f rational-affine. Record each with its source location.
Step 3. Classify: genuine cap vs design choice vs constructed edge
        (section 5). Only genuine caps become fail atoms.
Step 4. Detect scope boundaries: any condition that is not
        rational-affine in the declared coordinates (transcendental
        constants, numerically evaluated positivity, zero-density
        exponents) marks the edge of the certifiable layer. Stop there
        and document it.
Step 5. Encode, choosing slices that bracket every published threshold,
        including thresholds of the paper's intermediate theorems as
        ablations where the toolkit difference is a tool subset.
Step 6. Run (`python check.py library/INSTANCE.json`). Exact
        reproduction of all published rationals = the transcription
        passes its acceptance test. Any mismatch is a finding: either
        a transcription error (fix and rerun) or a genuine discrepancy
        with the paper (investigate by hand; this is how the engine
        earns its keep as an auditor). The run writes its full
        evidence to INSTANCE.certify.txt; commit it.
Step 7. Mutation census (`check.py ... --deep`, or mutate.py and
        mutant_census.py standalone). Every coefficient is perturbed
        both ways; each survivor gets a computed reason code. Add the
        slices the census demands until no BRACKETABLE survivor
        remains. What survives then is the paper's certified slack,
        machine-checked -- do not classify survivors by hand, the
        census exists because hand classification was falsified.
Step 8. Audit note (INSTANCE_AUDIT.md). Hand-written, not tool
        output: linearity verdict, substitutions with the pin/free
        decision for each, facet map, errors found and whether they
        propagate, ablations, survivor classes -- citing the committed
        report for every witness location asserted.

The protocol's failure modes concentrate in steps 3 and 4 — telling
constraints from conventions, and spotting the linear regime's edge.
Those are judgment calls; the run in step 6 is arithmetic. That split
is what makes AI-assisted transcription safe: the judgment is audited
by a human against the paper, and the arithmetic audits itself.
