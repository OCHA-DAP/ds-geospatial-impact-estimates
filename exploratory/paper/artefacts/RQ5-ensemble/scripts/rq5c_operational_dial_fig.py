"""RQ5c — the operational dial: is combining products 'good enough'?

Combining IMPROVES precision, but improvement != usable. This figure asks the operational
question honestly. From the frozen six-member dial (rq5b_six_member.csv), for each rule:
  - coverage = share of real damage the list reaches (field recall, r=20 m)
  - cost     = field visits per verified damaged building found
             = flags / (flags that land on real damage) = 1 / precision(crowd-adjusted)
We plot cost vs coverage across the agreement dial and the single products, and mark an
honest 'triage-usable' band vs a 'work-order' band, so the reader judges 'good enough'.

Cost uses crowd-adjusted precision (the fairer numerator: CEMS alone over-counts false
alarms, RQ2). Single products and k-of-6 rules on the same axes.

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ5-ensemble/scripts/rq5c_operational_dial_fig.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
df = pd.read_csv(os.path.join(HERE, "..", "rq5b_six_member.csv"))

SINGLES = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
kof = df[df.rule.str.fullmatch(r"\d-of-6")].copy()
kof["k"] = kof.rule.str[0].astype(int)
kof = kof.sort_values("k")
singles = df[df.rule.isin(SINGLES)]


def cost(p):  # field visits per verified damaged building found = 1 / precision
    return 1.0 / p if p and p > 0 else np.nan


fig, ax = plt.subplots(figsize=(10.5, 8))

# honest operational bands (visits per verified find)
ax.axhspan(1, 3, color="#2e7d32", alpha=0.07, zorder=0)
ax.axhspan(3, 8, color="#f9a825", alpha=0.07, zorder=0)
ax.axhspan(8, 100, color="#c62828", alpha=0.05, zorder=0)
ax.text(0.985, 2.0, "work-order zone (≤3 visits per real find)", fontsize=9.5,
        color="#2e7d32", va="center", ha="right")
ax.text(0.985, 5.0, "triage-usable (3–8)", fontsize=9.5, color="#b8860b",
        va="center", ha="right")
ax.text(0.985, 22, "not worth the walk (>8 visits per find)", fontsize=9.5,
        color="#c62828", va="center", ha="right")

# each rule spans a cost BAND: crowd-adjusted (optimistic, low) -> CEMS floor (pessimistic, high)
def band(sub, color, size, marker, label_pts=False):
    for i, (_, r) in enumerate(sub.iterrows()):
        x = r.R_field_r20
        lo, hi = cost(r.P_crowd_adj), cost(r.P_cems)
        ax.plot([x, x], [lo, hi], c=color, lw=2.2, alpha=0.5, zorder=3)
        ax.plot(x, hi, marker="_", ms=11, c=color, zorder=3)  # CEMS-floor cost (worst)

# single products: faint bands + dots at crowd-adjusted (fair) cost
for _, r in singles.iterrows():
    x = r.R_field_r20
    ax.plot([x, x], [cost(r.P_crowd_adj), cost(r.P_cems)], c="#9aa5b1", lw=1.6,
            alpha=0.6, zorder=2)
    ax.scatter(x, cost(r.P_crowd_adj), c="#4a5560", s=70, zorder=4)
    ax.annotate(r.rule, (x, cost(r.P_crowd_adj)), textcoords="offset points",
                xytext=(6, 3), fontsize=9, color="#4a5560")
ax.scatter([], [], c="#4a5560", s=70, label="single products")

# k-of-6 dial: bold bands, square at crowd-adjusted, tick at CEMS floor
kx = kof.R_field_r20.to_numpy()
for _, r in kof.iterrows():
    x = r.R_field_r20
    ax.plot([x, x], [cost(r.P_crowd_adj), cost(r.P_cems)], c="#2a78d6", lw=3,
            alpha=0.35, zorder=3)
ax.plot(kx, [cost(p) for p in kof.P_crowd_adj], c="#2a78d6", lw=1.6, zorder=4)
ax.scatter(kx, [cost(p) for p in kof.P_crowd_adj], c="#2a78d6", s=200, marker="s",
           zorder=5, label="k-of-6 agreement (k in square)")
# label the two ends of the band once, on the 1-of-6 rule
r1 = kof[kof.k == 1].iloc[0]
ax.annotate("strict: counts only\nexpert-recorded damage\n(= the '10–20 per hit' figure)",
            (r1.R_field_r20, cost(r1.P_cems)), textcoords="offset points",
            xytext=(-12, -6), ha="right", fontsize=9, color="#8a5a00")
ax.annotate("best estimate: also counts\ndamage the expert missed\n(crowd-confirmed)",
            (r1.R_field_r20, cost(r1.P_crowd_adj)), textcoords="offset points",
            xytext=(-12, 4), ha="right", fontsize=9, color="#2e7d32")
for _, r in kof.iterrows():
    ax.annotate(str(int(r.k)), (r.R_field_r20, cost(r.P_crowd_adj)),
                ha="center", va="center", fontsize=10, color="white", zorder=6)

ax.set_yscale("log")
ax.set_xlim(0, 1.0)
ax.set_ylim(1, 60)
ax.set_xlabel("coverage — share of field-verified damage the list reaches (r = 20 m)",
              fontsize=12)
ax.set_ylabel("cost — field visits per damaged-or-destroyed building found\n"
              "(log scale; lower = better)", fontsize=11)
ax.set_yticks([1, 2, 3, 5, 8, 15, 30, 60])
ax.set_yticklabels([1, 2, 3, 5, 8, 15, 30, 60])
ax.tick_params(labelsize=11)
ax.legend(fontsize=10, loc="upper center")
ax.set_title("Is combining products 'good enough'?  Target: damaged OR destroyed "
             "buildings (CEMS classes 2–3).\n"
             "Best case (Caraballeda). Each bar = the honest cost range; "
             "no rule is both cheap and complete.", fontsize=11.5)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq5c_operational_dial.png"), dpi=150)
print("wrote rq5c_operational_dial.png")
for _, r in kof.iterrows():
    print(f"  {int(r.k)}-of-6: coverage {r.R_field_r20:.2f} | "
          f"visits/find {cost(r.P_crowd_adj):.1f}–{cost(r.P_cems):.1f}")
