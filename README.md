# Exponent Threshold Certification
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21984728-blue.svg)](https://doi.org/10.5281/zenodo.21984728)
[![check-library](https://github.com/michaelmross/exponent-certificates/actions/workflows/check.yml/badge.svg)](https://github.com/michaelmross/exponent-certificates/actions/workflows/check.yml)

A tool for certifying published exponent thresholds in analytic number theory as exact linear-programming facets, together with a growing library of certified papers.

Companion note: [A Tool for Certifying Exponent Thresholds as Exact Linear-Programming Facets](https://doi.org/10.5281/zenodo.21986255)

Many theorems in this area have the shape "the result holds for c below some odd-looking fraction." That fraction is almost never explained. It is the output of a system of competing inequalities, and the paper typically prints the winning condition and moves on. This repository turns the system of inequalities itself into data (a JSON file), and an engine (`certify.py`) recomputes the threshold from that data by exact rational arithmetic, with no floating point anywhere. When the recomputed threshold matches the published one at every tested parameter value, the certificate passes. When it does not, either the transcription is wrong or the paper is, and both outcomes have happened.

A certificate does more than confirm the headline number. It identifies which condition actually produces the threshold (the binding facet), which printed conditions turn out never to matter (slack, or vacuous), what happens when each estimate is deleted (ablations), and which coefficients the certificate genuinely pins down as opposed to merely carries (the mutation census). The audit notes in this repository record several findings of exactly these kinds in the certified papers, none affecting the theorems, all invisible without doing this.

## What is in the repository

The engine and its harness are `certify.py` (the certifier), `mutate.py` (perturbs every coefficient and reruns), `mutant_census.py` (classifies why each perturbation was or was not caught), and `check.py` (runs everything). JSON instances live in `library/`. The CI configuration in `.github/workflows/check.yml` runs the fast pass on every push. `SCHEMA.md` documents the instance format and the transcription discipline.

Each certified paper contributes an instance file such as `heath_brown.json`, an audit note such as `heath_brown_AUDIT.md` recording what was found, and three machine-generated result files: the full certification report `*.certify.txt`, and the mutation results `*.mutation.tsv` and `*.census.tsv`. Two instances whose names begin with `CONTROL` are deliberately broken and must fail. They exist to prove the engine can detect error, and the workflow treats their failure as success.

## Command reference

Everything needs only Python 3, no packages. There is one entry point, `check.py`, and two tools it orchestrates that can also be run directly.

```
python check.py --library                  Certify every instance in /library, controls included.
                                           Run after any edit. (This is also what CI runs on every push.)
                                           Execution time: seconds.
python check.py --library --deep           Full pipeline on every instance: certify, fresh mutation run,
                                           mutant census. Run before a release or after changing slices                            
                                           or the harness.
                                           Execution time: minutes                                      
python check.py library/foo.json           One instance, certify only.
python check.py library/foo.json --deep    One instance, full pipeline.
```

`check.py` also lints before certifying (structural JSON problems fail loudly, style problems warn) and flags any committed `.mutation.tsv` whose row count no longer matches the instance, so a stale result file fails the consistency check rather than silently documenting an old version. Every certify run writes its full report to `INSTANCE.certify.txt` beside the instance (suppress with `--no-report`): witness locations, binding atoms, and per-slice checks, committed like the TSVs so every fact an audit note cites is a diffable artifact. Because the output is deterministic, the checker treats any byte change against the committed report as a failure even when the verdict still passes, which catches a moved witness or a changed check count that the verdict alone cannot see. An instance whose name begins with `CONTROL` must fail certification, and the checker reports it as OK only when the engine actually ran and mismatched.

The two underlying tools are standalone, and there are two situations where running them directly is the right choice. First, long mutation runs: `python mutate.py library/foo.json --chunk 2/4` runs a quarter of the mutants and appends to the TSV, which is how large instances are done under a timeout. Note that mutate.py always appends, by design, so delete the TSV before a fresh un-chunked run (`--deep` does this for you). Second, the bracket-placement loop: `python mutant_census.py library/foo.json` recomputes every verdict from the instance alone, without needing a mutation run, so while placing slices the cheap cycle is edit, census, check that BRACKETABLE is gone, repeat, and only then one `--deep` to regenerate the committed TSVs.

## The workflow for certifying a new paper

The word workflow here means the human procedure. The tool automates steps 2 and 4 of it; steps 1, 3 and 5 cannot be mechanized and are the actual work.

**Step 1, Transcribe.** Read the source document and extract every inequality that participates in the threshold, writing each as a linear constraint in the block coordinates with a right-hand side affine in the parameter. Record the paper's own design substitutions (a fixed exponent pair, a truncation height, a splitting parameter) and either hard-code the value as a constant or promote it to a block variable to be certified. The rules for doing this are in `SCHEMA.md`, and the existing JSON instances are the worked examples. A capable AI assistant can be tasked with executing this procedure.

**Step 2, Certify.** Execute `python check.py library/myinstance.json`. The engine recomputes everything the instance claims and compares against what it declares, in exact arithmetic, and the run either passes or names the first slice where expectation and arithmetic part ways. A mismatch means a transcription error or a paper error, and telling them apart is step 1's author's problem, not the engine's: the engine cannot distinguish a wrong encoding from a wrong paper, only a system from its declared threshold.

**Step 3, Cross-check if warranted.** For a result that matters, reproduce the verdict by an independent route before trusting it. For a one-variable coverage instance the natural route is a direct interval scan: At each fixed parameter value every constraint collapses to an interval condition on the variable, so witness existence is just the nonemptiness of an intersection of intervals, computable in a few dozen lines of exact rational arithmetic written from `SCHEMA.md` rather than from `certify.py`'s code. Agreement between two independent implementations tests the specification; running the same engine twice tests nothing.

**Step 4, Mutate and census.** `python check.py library/myinstance.json --deep`, or the standalone loop described in the command reference. The mutation run perturbs every coefficient by 1/50th in both directions and records which perturbations some slice catches (killed) and which survive. The census then classifies every survivor: UNOBSERVABLE means no slice placement could ever catch it, because the coefficient sits in certified slack, and this class is mathematical content, since it coincides with the paper's non-binding conditions. BRACKETABLE means a slice placed in the reported interval would catch it, so add that slice to the instance and rerun until no BRACKETABLE survivors remain. OUT_OF_REACH means the perturbation moves a boundary by less than the gap to the nearest slice-observable change. The goal state is zero BRACKETABLE, everything else explained.

**Step 5, Write the audit note.** This is a best practice, and the library contains several example audit notes. The automated pipeline ends at the `.certify.txt` report and the TSVs, and the audit note is the interpretation. Write `myinstance_AUDIT.md` recording the linearity verdict, the design substitutions and their provenance, the facet map with the binding facet and runner-up, any errors found in the paper and whether they propagate, the ablation results, and the survivor classification. Comments carry the transcription decisions a future auditor needs in order to re-derive the encoding from the paper.

## What a passing certificate does and does not assert

It asserts that the declared threshold is exactly the boundary of witness existence for the transcribed system, at every slice, in exact arithmetic, and that the killed coefficients are pinned against perturbation. It does not assert that the transcription faithfully encodes the paper. That soundness obligation belongs to the instance author.

Disclosure: This tool and documentation (including library audit notes) was created with the assistance of Claude (Anthropic) Fable 5.
