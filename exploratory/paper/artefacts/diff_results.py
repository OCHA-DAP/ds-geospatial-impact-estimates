"""Diff results.csv against the same table built from another git ref's per-script CSVs.

Usage: python diff_results.py --base origin/v1 [--out _audit/diff_<ref>.md]
Builds results at <base> by checking out that ref's copies of every consolidate input into a
temp dir and running consolidate there, then reports every changed value with the brief keys
that read it (keys are looked up by re-importing brief_numbers against each table).
"""
import argparse, os, subprocess, sys, tempfile, shutil, importlib.util
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True, cwd=HERE).strip()
REL = os.path.relpath(HERE, ROOT)

def build_at(ref: str, tmp: str) -> pd.DataFrame:
    spec = importlib.util.spec_from_file_location("consolidate", os.path.join(HERE, "consolidate.py"))
    cons = importlib.util.module_from_spec(spec); spec.loader.exec_module(cons)
    # copy this consolidator, fetch every input from the ref
    shutil.copy(os.path.join(HERE, "consolidate.py"), tmp)
    # Old refs only have the per-RQ CSVs, so the table at <base> is built the oracle way
    # (consolidate.py --oracle); learn which CSVs that reads by running those sources here.
    cons.LOADED.clear()
    for fn in cons.ORACLE_SOURCES:   # discovery only: a stale archive file may trip a source's own anchor here; that is not this tool's concern
        try:
            fn()
        except (SystemExit, Exception):
            pass
    inputs = {rel for rel in cons.LOADED if not rel.startswith("../pipeline/")}
    missing = []
    for rel in sorted(inputs):
        os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
        try:
            blob = subprocess.check_output(["git", "show", f"{ref}:{REL}/{rel}"], cwd=ROOT, stderr=subprocess.DEVNULL)
            open(os.path.join(tmp, rel), "wb").write(blob)
        except subprocess.CalledProcessError:
            missing.append(rel)
    if missing:
        print(f"note: {len(missing)} inputs absent at {ref}: {missing}")
        for rel in missing:  # write an empty frame with the current header so the source function raises a clear error
            hdr = open(os.path.join(HERE, rel)).readline()
            open(os.path.join(tmp, rel), "w").write(hdr)
    # column names that changed between refs (ADR-0031 renamed the crowd column)
    COMPAT = {"P_crowd_adj": "P_crowd", "P_crowd_adj_r1": "P_crowd_r1", "P_crowd_adj_r2swap": "P_crowd_r2swap"}
    for rel in sorted(inputs):
        f = os.path.join(tmp, rel)
        df = pd.read_csv(f)
        ren = {k: v for k, v in COMPAT.items() if k in df.columns and v not in df.columns}
        if ren:
            df.rename(columns=ren).to_csv(f, index=False)
    r = subprocess.run([sys.executable, "consolidate.py", "--oracle"], cwd=tmp, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"consolidate --oracle failed at {ref}:\n{r.stderr[-2000:]}")
    return pd.read_csv(os.path.join(tmp, "results_oracle_frozen.csv"))

def expectations_footprint_rule(m: pd.DataFrame) -> list:
    """Expectations for the one-rule footprint mapping (IoU 1:1 for MS, UNEP, UH; 2026-09-14) against
    the previous commit, where only Microsoft was re-mapped (largest overlap)."""
    def sel(region, lens, radius, metric, preds):
        q = m[(m.region == region) & (m.lens == lens) & (m.radius == radius) & (m.metric == metric) & (m._merge == "both")]
        return q[q.predictor.isin(preds)]
    out = []
    for metric in ("P", "R", "n_flags"):
        d = sel("core", "points", 10, metric, ["IMPACT", "OSU", "LIST"])
        out.append((f"IMPACT/OSU/LIST core {metric} unchanged (id-mapped products untouched)", bool((d.value_now == d.value_base).all()), f"{len(d)} rows"))
    d = sel("core", "points", 10, "n_flags", ["MS"]); out.append(("Microsoft core flags move by <= 25 (largest-overlap -> IoU)", bool(((d.value_now - d.value_base).abs() <= 25).all()), f"{d.value_base.iloc[0]:g} -> {d.value_now.iloc[0]:g}"))
    d = sel("core", "points", 10, "n_flags", ["UH"]); out.append(("UH core flags move by <= 2% (rule 3 snaps ~1,000 footprints gold's containment rule dropped)", bool(((d.value_now - d.value_base).abs() / d.value_base <= 0.02).all()), f"{d.value_base.iloc[0]:g} -> {d.value_now.iloc[0]:g}"))
    d = sel("core", "points", 10, "n_flags", ["UNEP"]); out.append(("UNEP core flags move by <= 4%", bool(((d.value_now - d.value_base).abs() / d.value_base <= 0.04).all()), f"{d.value_base.iloc[0]:g} -> {d.value_now.iloc[0]:g}"))
    d = sel("core", "points", 10, "P", ["MS", "UH", "UNEP"]); out.append(("MS/UH/UNEP core precision moves by <= 0.01", bool(((d.value_now - d.value_base).abs() <= 0.01).all()), f"max |Δ| {(d.value_now - d.value_base).abs().max():.3f}"))
    d = m[(m.lens == "cells") & (m.metric == "rho") & (m._merge == "both")]; out.append(("area-ranking correlations move by <= 0.02", bool(((d.value_now - d.value_base).abs() <= 0.02).all()), f"max |Δ| {(d.value_now - d.value_base).abs().max():.3f}"))
    d = m[(m.lens == "facts") & (m.predictor == "CEMS") & (m._merge == "both")]; out.append(("reference-point facts unchanged", bool((d.value_now == d.value_base).all()), f"{len(d)} rows"))
    return out


EXPECTATION_SETS = {"live": None, "footprint-rule": expectations_footprint_rule}   # "live" = the ADR-0030/0031 set below


def expectations(m: pd.DataFrame) -> list:
    """Declared expectations for the ADR-0030/0031 refreeze against the live (v1) numbers.
    Each returns (name, passed, detail). Edit this list when the next change has different
    expected directions; the report shows PASS/FAIL per expectation."""
    P6 = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
    def sel(region, lens, radius, metric, preds=None):
        q = m[(m.region == region) & (m.lens == lens) & (m.radius == radius) & (m.metric == metric) & (m._merge == "both")]
        q = q[q.predictor.isin(preds)] if preds else q
        if not len(q):
            raise SystemExit(f"expectations: no rows for {region}/{lens}/{radius}/{metric} in both tables — is the base ref comparable?")
        return q
    out = []
    d = sel("core", "points", 10, "P", P6); out.append(("core precision rises for all six products (footprint frame)", bool((d.value_now > d.value_base).all()), f"{len(d)} products"))
    d = sel("core", "points", 10, "R", P6); out.append(("core recall rises for all six products", bool((d.value_now > d.value_base).all()), f"{len(d)} products"))
    d = sel("core", "points", 10, "n_flags", ["MS"]); out.append(("Microsoft core flags fall (1:1 mapping removes neighbour bleed)", bool((d.value_now < d.value_base).all()), f"{d.value_base.iloc[0]:g} -> {d.value_now.iloc[0]:g}" if len(d) else "n/a"))
    d = sel("core", "points", 10, "n_flags", [p for p in P6 if p != "MS"]); out.append(("other products' core flag counts move by <= 3", bool(((d.value_now - d.value_base).abs() <= 3).all()), f"max |Δ| {(d.value_now - d.value_base).abs().max():g}"))
    d = sel("core", "points", 10, "F1", [f"{k}-of-6" for k in range(3, 7)]); out.append(("agreement-rule F1 rises for k >= 3", bool((d.value_now > d.value_base).all()), f"{len(d)} rules"))
    d = m[(m.lens == "cells") & (m.metric == "rho") & (m._merge == "both") & (m.predictor != "Microsoft")]; out.append(("area-ranking correlations move by <= 0.011 for products whose flags did not change", bool(((d.value_now - d.value_base).abs() <= 0.011).all()), f"max |Δ| {(d.value_now - d.value_base).abs().max():.3f} over {len(d)} rows"))
    d = m[(m.lens == "cells") & (m.metric == "rho") & (m._merge == "both") & (m.predictor == "Microsoft")]; out.append(("Microsoft's area-ranking correlations move by <= 0.02 (its flag set changed)", bool(((d.value_now - d.value_base).abs() <= 0.02).all()), f"max |Δ| {(d.value_now - d.value_base).abs().max():.3f} over {len(d)} rows"))
    d = sel("core", "bounds", 10, "P_upper", P6); out.append(("upper-bound precision rises for all six", bool((d.value_now > d.value_base).all()), ""))
    pc, pf = sel("core", "bounds", 10, "P_crowd", ["MS"]), sel("core", "bounds", 10, "P_floor", ["MS"])
    inc_b, inc_n = float(pc.value_base.iloc[0] - pf.value_base.iloc[0]), float(pc.value_now.iloc[0] - pf.value_now.iloc[0])
    out.append(("Microsoft's crowd increment (P_crowd − P_floor) moves by <= 0.015 (99% reviewed, so ADR-0031 changes nothing for it)", abs(inc_n - inc_b) <= 0.015, f"{inc_b:.3f} -> {inc_n:.3f}"))
    d = m[(m.lens == "field") & (m.metric == "R") & (m._merge == "both") & m.predictor.isin(["MS", "IMPACT v2", "OSU", "UH", "LIST"])]; out.append(("field recall rises for every product at every radius", bool((d.value_now >= d.value_base).all()), f"{len(d)} rows"))
    d = sel("asd", "crowd-round2", 10, "conf_r1", ["MS"]); out.append(("crowd confirmation share in the strip moves by <= 0.01", bool(((d.value_now - d.value_base).abs() <= 0.01).all()), f"Δ {float(d.value_now.iloc[0] - d.value_base.iloc[0]):+.3f}" if len(d) else "n/a"))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="origin/v1"); ap.add_argument("--out")
    ap.add_argument("--expect", default="live", choices=list(EXPECTATION_SETS), help="which declared expectation set to check")
    a = ap.parse_args()
    now = pd.read_csv(os.path.join(HERE, "results.csv"))
    with tempfile.TemporaryDirectory() as tmp:
        base = build_at(a.base, tmp)
    key = ["region", "lens", "radius", "predictor", "metric"]
    m = base.merge(now, on=key, how="outer", suffixes=("_base", "_now"), indicator=True)
    changed = m[(m._merge == "both") & (m.value_base != m.value_now)]
    added = m[m._merge == "right_only"]; gone = m[m._merge == "left_only"]
    out = a.out or os.path.join(HERE, "_audit", f"diff_{a.base.replace('/', '_')}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lines = [f"# results.csv: {a.base} → working tree", "", f"{len(changed)} changed, {len(added)} added, {len(gone)} removed (of {len(now)} rows)", "",
             "| region | lens | r | predictor | metric | base | now | Δ | source |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in changed.sort_values(["source_now", *key]).iterrows():
        lines.append(f"| {r.region} | {r.lens} | {r.radius} | {r.predictor} | {r.metric} | {r.value_base:g} | {r.value_now:g} | {r.value_now - r.value_base:+.3f} | {r.source_now} |")
    exp = (EXPECTATION_SETS[a.expect] or expectations)(m)
    lines += ["", "## expectations", "", "| expectation | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {'PASS' if ok else '**FAIL**'} | {det} |" for n, ok, det in exp]
    print(f"expectations: {sum(ok for _, ok, _ in exp)}/{len(exp)} pass")
    if len(added): lines += ["", "## added", ""] + [f"- {' / '.join(str(r[k]) for k in key)} = {r.value_now:g}" for _, r in added.iterrows()]
    if len(gone): lines += ["", "## removed", ""] + [f"- {' / '.join(str(r[k]) for k in key)} = {r.value_base:g}" for _, r in gone.iterrows()]
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{len(changed)} changed, {len(added)} added, {len(gone)} removed → {out}")

if __name__ == "__main__":
    main()
