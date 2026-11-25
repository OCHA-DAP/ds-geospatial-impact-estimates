"""RQ2m — why precision falls outside Caraballeda: dead-zone dilution.

96% of CEMS damage is in Caraballeda; the other four CEMS AOIs hold ~46 damage points
total, so precision there is ~0 (any flag is a false positive). Pooled (as-delivered)
precision is a flag-weighted average, so it falls by almost exactly the SHARE of a
product's flags that land in those dead zones. This shows the near-perfect law and answers
"shouldn't precision get ripped up outside Caraballeda?" — yes, in proportion to where you
flag. Reads rq2i_per_aoi_scorecard.csv (no compute).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2m_deadzone_dilution.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
df = pd.read_csv(os.path.join(HERE, "..", "rq2i_per_aoi_scorecard.csv"))
allrow = df[df.aoi == "ALL (as delivered)"].set_index("product")
car = df[df.aoi == "Caraballeda"].set_index("product")

PRODS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
COL = {"MS": "#c62828", "IMPACT": "#4a90d9", "OSU": "#2a78d6",
       "UH": "#e08214", "LIST": "#2e8b57", "UNEP": "#8a5a00"}
rows = []
for p in PRODS:
    fc, fa = car.loc[p, "n_flags"], allrow.loc[p, "n_flags"]
    pc, pa = car.loc[p, "P_cems"], allrow.loc[p, "P_cems"]
    rows.append(dict(product=p, dead_share=100 * (fa - fc) / fa,
                     prec_lost=100 * (pc - pa) / pc if pc else 0,
                     pc=pc, pa=pa, dead=int(fa - fc)))
t = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(9, 7.5))
ax.plot([0, 100], [0, 100], ls="--", color="#bbb", lw=1.8, zorder=1,
        label="precision lost = share of flags in dead zones")
off = {"UNEP": (10, 4), "LIST": (-20, 20), "IMPACT": (12, -26), "OSU": (12, 2),
       "MS": (12, 0), "UH": (-12, 12)}
for _, r in t.iterrows():
    ax.scatter(r.dead_share, r.prec_lost, s=170, color=COL[r["product"]], zorder=4,
               edgecolor="white", lw=1.2)
    ax.annotate(f"{r['product']}\n{r.pc:.3f} → {r.pa:.3f}",
                (r.dead_share, r.prec_lost), textcoords="offset points",
                xytext=off.get(r["product"], (10, 0)), fontsize=11,
                color=COL[r["product"]], weight="bold")
ax.set_xlim(-4, 104); ax.set_ylim(-4, 104)
ax.set_xlabel("share of the product's flags that land OUTSIDE Caraballeda\n"
              "(in the four CEMS AOIs with ~zero damage)", fontsize=12)
ax.set_ylabel("precision lost vs Caraballeda  (%)", fontsize=12)
ax.tick_params(labelsize=11)
ax.legend(fontsize=11, loc="lower right")
ax.set_title("Precision falls by exactly the share of flags wasted on dead zones\n"
             "Outside Caraballeda CEMS reports almost no damage — so every flag there is a "
             "false positive.\nMS is spared only because it flagged nowhere else.",
             fontsize=12.5)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq2m_deadzone_dilution.png"), dpi=150)
print("wrote rq2m_deadzone_dilution.png")
print(t.to_string(index=False))
