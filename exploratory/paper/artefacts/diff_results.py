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
    inputs = set()
    src = open(os.path.join(HERE, "consolidate.py")).read()
    import re
    for rel in re.findall(r'"(RQ[^"]+\.csv)"', src): inputs.add(rel)
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
    r = subprocess.run([sys.executable, "consolidate.py"], cwd=tmp, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"consolidate failed at {ref}:\n{r.stderr[-2000:]}")
    return pd.read_csv(os.path.join(tmp, "results.csv"))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="origin/v1"); ap.add_argument("--out")
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
    if len(added): lines += ["", "## added", ""] + [f"- {' / '.join(str(r[k]) for k in key)} = {r.value_now:g}" for _, r in added.iterrows()]
    if len(gone): lines += ["", "## removed", ""] + [f"- {' / '.join(str(r[k]) for k in key)} = {r.value_base:g}" for _, r in gone.iterrows()]
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{len(changed)} changed, {len(added)} added, {len(gone)} removed → {out}")

if __name__ == "__main__":
    main()
