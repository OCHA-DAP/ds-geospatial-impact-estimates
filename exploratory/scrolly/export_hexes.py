"""Hex layer for the ranking beat: per res-8 cell, expert damage count vs 3+-agreement count."""
import pandas as pd, json, h3
from pathlib import Path
df = pd.read_parquet("exploratory/paper/artefacts/RQ8-learned-fusion/rq8_oof_scores_r10.parquet")
flags = [c for c in df.columns if c.startswith("flag_")]
df["k"] = df[flags].sum(axis=1).astype(int)
df["cell"] = [h3.latlng_to_cell(la, lo, 8) for la, lo in zip(df.lat, df.lon)]
g = df.groupby("cell").agg(n=("k","size"), e=("y","sum"), a=("k", lambda s: int((s>=3).sum())))
g = g[g.n >= 20].copy()
g["pe"] = g.e.rank(pct=True); g["pa"] = g.a.rank(pct=True)
feats = []
for cell, r in g.iterrows():
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    feats.append({"type":"Feature","properties":{"e":int(r.e),"a":int(r.a),
                  "pe":round(r.pe,3),"pa":round(r.pa,3)},
                  "geometry":{"type":"Polygon","coordinates":[ring]}})
rho = g[["e","a"]].corr(method="spearman").iloc[0,1]
out = Path(__file__).parent / "hexes.js"
out.write_text("const HEXES = " + json.dumps({"type":"FeatureCollection","features":feats},
               separators=(",",":")) + ";\n")
print(f"cells: {len(g)} | spearman e~a: {rho:.3f} | KB: {out.stat().st_size//1024}")
