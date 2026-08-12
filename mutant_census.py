#!/usr/bin/env python3
"""mutant_census.py -- annotate a coverage-mode mutation run with kill
provenance and computed survivor classification.

For every mutant of an instance (same generator as mutate.py), computes by
exact 1-D interval arithmetic the witness-existence boundary set of base
and mutant in every configuration (base toolkit + each ablation), then:

  killed    -> records the first (slice, configuration) whose expectation
               flips, and the boundary that moved.
  SURVIVED  -> a reason code:
     UNOBSERVABLE   boundary sets identical to base in every configuration:
                    no slice placement could ever kill this mutant
                    (dominated fail option, masked atom, slack interior).
     OUT_OF_REACH   some boundary moved, but no admissible slice between
                    the base and mutant boundary exists with a flipped
                    expectation (movement smaller than the gap to the
                    nearest expectation change).
     BRACKETABLE    a boundary moved and a slice placed in the gap WOULD
                    kill: lists the killing interval. These are the only
                    survivors that better slices can convert.

Output: INSTANCE.census.tsv, one row per mutant:
  label  verdict  detail
Cross-checks its verdicts against mutate.py's INSTANCE.mutation.tsv when
present and reports any disagreement (there should be none).

Coverage mode, one variable, only. Level mode needs no bracket census:
every slice checks an exact equality, so any observable shift kills at
the slice itself and survivors are UNOBSERVABLE by definition.
"""
import json, sys, copy, os
from fractions import Fraction as F

EPS = (F(1,50), F(-1,50))
NEG = POS = None

def half(c, r0, r1, g):
    rhs = r0 + r1*g
    if c == 0: return [(NEG,POS)] if 0 <= rhs else []
    return [(NEG, rhs/c)] if c > 0 else [(rhs/c, POS)]

def inter(a,b):
    out=[]
    for (x1,y1) in a:
        for (x2,y2) in b:
            lo = x1 if x2 is None else (x2 if x1 is None else max(x1,x2))
            hi = y1 if y2 is None else (y2 if y1 is None else min(y1,y2))
            if lo is None or hi is None or lo <= hi: out.append((lo,hi))
    return out

def parse(at): return F(at[0][0]), F(at[1][0]), F(at[1][1])

def witness(inst, g, removed):
    for p in inst["pieces"].values():
        reg=[(NEG,POS)]
        for at in p["region"]:
            c,r0,r1 = parse(at); reg = inter(reg, half(c,r0,r1,g))
        if not reg: continue
        cur=reg
        for t in p["tools"]:
            if t in removed: continue
            fs=[]
            for opt in inst["tools"][t]["fail_options"]:
                o=[(NEG,POS)]
                for at in opt:
                    c,r0,r1 = parse(at); o = inter(o, half(c,r0,r1,g))
                fs += o
            cur = inter(cur, fs)
            if not cur: break
        if cur: return True
    return False

def boundaries(inst, removed, lo=F(0), hi=F(1), grid=800, iters=64):
    G=[lo+(hi-lo)*F(i,grid) for i in range(grid+1)]
    V=[witness(inst,g,removed) for g in G]
    out=[]
    for i in range(grid):
        if V[i]!=V[i+1]:
            a,b=G[i],G[i+1]
            for _ in range(iters):
                m=(a+b)/2
                if witness(inst,m,removed)==V[i]: a=m
                else: b=m
            out.append(((a+b)/2, V[i], V[i+1]))   # (location~, left value, right value)
    return out

def configs(inst):
    cfg=[("base",())]
    for name,a in inst.get("ablations",{}).items():
        cfg.append((name, tuple(a["remove_tools"])))
    return cfg

def expected(inst, cname, g):
    if cname=="base":
        thr=F(inst["expected_coverage"]["threshold"]); iff=inst["expected_coverage"]["witness_iff"]
    else:
        thr=F(inst["ablations"][cname]["expected_threshold"]); iff=inst["expected_coverage"]["witness_iff"]
    return (g<=thr) if iff=="le" else (g>=thr)

def mutants(spec):
    for tname,tool in spec.get("tools",{}).items():
        for oi,opt in enumerate(tool["fail_options"]):
            for ai,atom in enumerate(opt):
                for ri,val in enumerate(atom[1]):
                    for eps in EPS:
                        m=copy.deepcopy(spec)
                        m["tools"][tname]["fail_options"][oi][ai][1][ri]=str(F(str(val))+eps)
                        yield (f"tool:{tname}/opt{oi}/atom{ai}/rhs{ri}{'+' if eps>0 else '-'}", m)
    for pname,piece in spec.get("pieces",{}).items():
        for ci,con in enumerate(piece["region"]):
            for ri,val in enumerate(con[1]):
                for eps in EPS:
                    m=copy.deepcopy(spec)
                    m["pieces"][pname]["region"][ci][1][ri]=str(F(str(val))+eps)
                    yield (f"region:{pname}/row{ci}/rhs{ri}{'+' if eps>0 else '-'}", m)

def main(path):
    spec=json.load(open(path))
    slices=[F(s) for s in spec["slices"]]
    cfgs=configs(spec)
    base_b={c: boundaries(spec,rem) for c,rem in cfgs}
    rows=[]
    for label,m in mutants(spec):
        verdict=None; detail=""
        # 1) direct kill check at declared slices
        for cname,rem in cfgs:
            for g in slices:
                if witness(m,g,rem)!=expected(spec,cname,g):
                    verdict="killed"
                    detail=(f"config={cname} slice={g} "
                            f"(mutant={'witness' if witness(m,g,rem) else 'covered'}, "
                            f"expected {'witness' if expected(spec,cname,g) else 'covered'})")
                    break
            if verdict: break
        if verdict is None:
            # 2) survivor classification via boundary comparison
            moved=[]
            for cname,rem in cfgs:
                mb=boundaries(m,rem)
                bb=base_b[cname]
                if len(mb)!=len(bb) or any(abs(x[0]-y[0])>F(1,10**12) for x,y in zip(mb,bb)):
                    moved.append((cname,bb,mb))
            if not moved:
                verdict="SURVIVED"; detail="UNOBSERVABLE (boundary set identical to base in every configuration)"
            else:
                # is there an admissible killing slice in some moved gap?
                brackets=[]
                for cname,bb,mb in moved:
                    rem=dict(cfgs)[cname]
                    pairs = list(zip(bb,mb)) if len(bb)==len(mb) else None
                    lohi=[]
                    if pairs:
                        for (x,_,_),(y,_,_) in pairs:
                            if abs(x-y)>F(1,10**12): lohi.append((min(x,y),max(x,y)))
                    else:
                        allb=sorted([b[0] for b in bb]+[b[0] for b in mb])
                        lohi=[(allb[i],allb[i+1]) for i in range(len(allb)-1)]
                    for lo,hi in lohi:
                        # sample interior: does mutant differ from expectation there?
                        g=(lo+hi)/2
                        if witness(m,g,rem)!=expected(spec,cname,g):
                            brackets.append(f"{cname}:({lo}..{hi})")
                if brackets:
                    verdict="SURVIVED"; detail="BRACKETABLE in "+" ; ".join(brackets[:3])
                else:
                    verdict="SURVIVED"; detail=("OUT_OF_REACH (boundary moved: "
                        + " ; ".join(f"{c}" for c,_,_ in moved[:3])
                        + " -- movement does not cross any expectation change)")
        rows.append((label,verdict,detail))
    out=path.replace(".json",".census.tsv")
    with open(out,"w") as f:
        f.write("mutant\tverdict\tdetail\n")
        for r in rows: f.write("\t".join(r)+"\n")
    # cross-check against mutate.py verdicts
    mt=path.replace(".json",".mutation.tsv")
    dis=0
    if os.path.exists(mt):
        got={l.split("\t")[0]:l.split("\t")[1].strip() for l in open(mt) if "\t" in l}
        for label,v,_ in rows:
            if label in got and got[label]!=v:
                dis+=1; print(f"  DISAGREE {label}: census={v} mutate={got[label]}")
    from collections import Counter
    cnt=Counter(v if v=="killed" else d.split(" ")[0] for _,v,d in rows)
    print(f"{path}: {dict(cnt)}  disagreements_with_mutate.py={dis}  -> {out}")

if __name__=="__main__":
    for p in sys.argv[1:]: main(p)
