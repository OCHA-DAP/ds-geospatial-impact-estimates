import pandas as pd, json
from pathlib import Path
df = pd.read_parquet("exploratory/paper/artefacts/RQ8-learned-fusion/rq8_oof_scores_r10.parquet")
flags = [c for c in df.columns if c.startswith("flag_")]
df["k"] = df[flags].sum(axis=1).astype(int)
# per row: lon, lat, k (0-6 agreement), y (expert label), ms (Microsoft flag)
order = ["flag_MS","flag_IMPACT","flag_OSU","flag_UH","flag_LIST","flag_UNEP"]
for c in order: df[c] = df[c].fillna(0).astype(int)
df["b"] = sum(df[c] * (2**i) for i, c in enumerate(order))
rows = [[round(r.lon,5), round(r.lat,5), r.k, int(r.y), int(r.flag_MS), int(r.b)] for r in df.itertuples()]
dmg = df[df.y == 1]
gx, gy = (dmg.lon*200).round()/200, (dmg.lat*200).round()/200
cara = pd.DataFrame({"x": gx, "y": gy}).value_counts().idxmax()
fl = df[df.k > 0]
ms = df.flag_MS.astype(bool); yy = df.y.astype(bool)
ms_p = int((ms & yy).sum()); ms_f = int((ms & ~yy).sum())
meta = {"coast_center": [float(fl.lon.mean()), float(fl.lat.mean())],
        "cara_center": [float(cara[0]), float(cara[1])],
        "counts": {"any": int((df.k>0).sum()), "k4": int((df.k>=4).sum()), "k6": int((df.k==6).sum()),
                   "total": len(df), "expert": int(df.y.sum()), "ms_hit": ms_p, "ms_miss": ms_f}}
out = Path(__file__).parent
out.joinpath("data.js").write_text("const META = " + json.dumps(meta) + ";\nconst PTS = " +
    json.dumps(rows, separators=(",", ":")) + ";\n")
print(meta["counts"], "| MB:", round(out.joinpath('data.js').stat().st_size/1e6, 2))
