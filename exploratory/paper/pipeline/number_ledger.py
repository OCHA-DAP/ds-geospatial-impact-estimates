"""For each artefact CSV changed vs the frozen tag, list cells whose value changed and
where the OLD formatted value appears in manuscript_brief.qmd (line numbers).
Usage: uv run --group etl python artefacts/number_ledger.py [csv ...]
"""
import io, re, subprocess, sys, pathlib
import pandas as pd
TAG = "paper-frozen-v3-centroid"
ROOT = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
brief = (ROOT / "exploratory/paper/manuscript_brief.qmd").read_text().splitlines()

def changed_csvs():
    out = subprocess.check_output(["git", "diff", "--name-only", TAG, "--", "exploratory/paper/artefacts"], text=True, cwd=ROOT)
    return [l for l in out.splitlines() if l.endswith(".csv")]

def fmt_variants(v):
    if isinstance(v, str): return {v}
    s = set()
    if float(v).is_integer(): s |= {f"{int(v)}", f"{int(v):,}"}
    for d in (2, 3): s.add(f"{v:.{d}f}"); s.add(f"{v:.{d}f}".lstrip("0") if abs(v) < 1 else "")
    s.discard("")
    return s

def find(s):
    pat = re.compile(rf"(?<![\d.]){re.escape(s)}(?![\d])")
    return [i + 1 for i, l in enumerate(brief) if pat.search(l)]

files = sys.argv[1:] or changed_csvs()
for rel in files:
    try: old = pd.read_csv(io.StringIO(subprocess.check_output(["git", "show", f"{TAG}:{rel}"], text=True, cwd=ROOT)))
    except subprocess.CalledProcessError: print(f"### {rel}: NEW file"); continue
    new = pd.read_csv(ROOT / rel)
    print(f"### {rel}  old {old.shape} new {new.shape}")
    if old.shape != new.shape or list(old.columns) != list(new.columns):
        print("   shape/columns differ; inspect by hand"); continue
    for c in new.columns:
        if not pd.api.types.is_numeric_dtype(new[c]): continue
        for i in range(len(new)):
            o, n = old[c].iloc[i], new[c].iloc[i]
            if pd.isna(o) and pd.isna(n) or o == n: continue
            key = " ".join(str(new[k].iloc[i]) for k in new.columns if not pd.api.types.is_numeric_dtype(new[k]))
            hits = sorted({ln for s in fmt_variants(o) if len(s) >= 3 for ln in find(s)})
            print(f"   {key:32s} {c:12s} {o!s:>10} -> {n!s:<10} brief lines: {hits if hits else '-'}")
