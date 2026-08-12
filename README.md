# exponent-certificates

A tool for certifying published exponent thresholds in analytic number theory as exact linear-programming facets, together with a growing library of certified papers.

Many theorems in this area have the shape "the result holds for c below some odd-looking fraction." That fraction is almost never explained. It is the output of a system of competing inequalities, and the paper typically prints the winning condition and moves on. This repository turns the system of inequalities itself into data (a JSON file), and an engine (`certify.py`) recomputes the threshold from that data by exact rational arithmetic, with no floating point anywhere. When the recomputed threshold matches the published one at every tested parameter value, the certificate passes. When it does not, either the transcription is wrong or the paper is, and both outcomes have happened.

A certificate does more than confirm the headline number. It identifies which condition actually produces the threshold (the binding facet), which printed conditions turn out never to matter (slack, or vacuous), what happens when each estimate is deleted (ablations), and which coefficients the certificate genuinely pins down as opposed to merely carries (the mutation census). The audit notes in this repository record several findings of exactly these kinds in the certified papers, none affecting the theorems, all invisible without doing this.

## What is in the repository

The engine and its harness are `certify.py` (the certifier), `mutate.py` (perturbs every coefficient and reruns), `mutant_census.py` (classifies why each perturbation was or was not caught), and `workflow.py` (runs everything). `SCHEMA.md` documents the instance format and the transcription discipline.

Each certified paper contributes an instance file such as `heath_brown.json`, an audit note such as `heath_brown_AUDIT.md` recording what was found, and two machine-generated result files, `*.mutation.tsv` and `*.census.tsv`. Two instances whose names begin with `CONTROL` are deliberately broken and must fail. They exist to prove the engine can detect error, and the workflow treats their failure as success.

## Running it

Everything needs only Python 3, no packages.

```
python3 workflow.py --all
```

certifies the entire library in about a minute and prints one line per instance. The expected output ends with `LIBRARY CONSISTENT`. Run this after any edit.

```
python3 workflow.py myinstance.json --deep
```

runs the full pipeline on one instance: certification, a fresh mutation run, and (for coverage instances) the mutant census. This takes minutes, and is the command to run once after finishing a new instance or changing its slices. `--all --deep` does it for the whole library and is a pre-release job, not a routine one.

## The workflow for certifying a new paper

**Step 1, transcribe.** Read the proof and extract every inequality that participates in the threshold, writing each as a linear constraint in the block coordinates with a right-hand side affine in the parameter. Record the paper's own design substitutions (a fixed exponent pair, a truncation height, a splitting parameter) and either pin them with provenance or free them so the certificate tests them. The rules for doing this honestly, including the sandwich discipline and the treatment of constructed edges, are in `SCHEMA.md`, and the existing instances are the worked examples. This step is the mathematics. Everything after it is checking.

**Step 2, certify.** Write the instance JSON with the published threshold declared in `expected_coverage` (or `expected_profile` for min-max instances), pick slices that include the threshold itself, values tightly bracketing it, every runner-up facet, and any validity edges. Then `python3 workflow.py myinstance.json`. A mismatch at this stage means a transcription error or a paper error, and telling them apart is step 1's problem, not the engine's.

**Step 3, cross-check if warranted.** For a result that matters, reproduce the verdict by an independent route before trusting it, for instance a direct interval scan written from the instance file rather than through `certify.py`. The Guo-Guo-Lu instance was checked this way at all sixty original checks.

**Step 4, mutation and census.** `python3 workflow.py myinstance.json --deep`. The mutation run perturbs every coefficient by 1/50 in both directions and records which perturbations some slice catches (killed) and which survive. The census then classifies every survivor: UNOBSERVABLE means no slice placement could ever catch it, because the coefficient sits in certified slack, and this class is mathematical content, since it coincides with the paper's non-binding conditions. BRACKETABLE means a slice placed in the reported interval would catch it, so add that slice to the instance and rerun until no BRACKETABLE survivors remain. OUT_OF_REACH means the perturbation moves a boundary by less than the gap to the nearest slice-observable change. The goal state is zero BRACKETABLE, everything else explained.

**Step 5, audit note.** Write `myinstance_AUDIT.md` recording the linearity verdict, the design substitutions and their provenance, the facet map with the binding facet and runner-up, any errors found in the paper and whether they propagate, the ablation results, and the survivor classification. The note is where findings live. The instance comment carries the transcription decisions a future auditor needs in order to re-derive the encoding from the paper.

A caution learned the hard way: the survivor classification was originally done by hand in the audit notes, and when `mutant_census.py` was written to mechanize it, it found ten survivors across two instances that the hand analysis had misclassified. The corrected notes keep the record of that. Classification belongs in code, prose belongs to interpretation.

## What a passing certificate does and does not assert

It asserts that the declared threshold is exactly the boundary of witness existence for the transcribed system, at every slice, in exact arithmetic, and that the killed coefficients are pinned against perturbation. It does not assert that the transcription faithfully encodes the paper. That soundness obligation belongs to the instance author and is discharged in prose, atom by atom, in the provenance fields. The engine certifies the arithmetic of the reachable set. It cannot certify the reach of mathematics.
