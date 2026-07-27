"""RQ5b frontier figure — six members, scorecard frame (dual-anchor r=10 m).

Replaces the stale four-member rq5_pr_frontier_r10.png in the manuscript. Reads the
frozen rq5b_six_member.csv only (no blob access). Styling matches the day-zero baseline
figure: grey dots = shipped products, numbered blue squares = k-of-6 voting rules.
Vertical whiskers show each rule's precision interval: CEMS-measured floor (marker) up
to crowd-adjusted precision (tick).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ5-ensemble/scripts/rq5b_frontier_fig.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

df = pd.read_csv(os.path.join(HERE, "..", "rq5b_six_member.csv"))
SINGLES = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
singles = df[df.rule.isin(SINGLES)]
pairs = df[df.rule.str.contains("∧")]
kof = df[df.rule.str.fullmatch(r"\d-of-6")].copy()
kof["k"] = kof.rule.str[0].astype(int)
kof = kof.sort_values("k")

fig, ax = plt.subplots(figsize=(10, 7.5))

# precision intervals: CEMS floor -> crowd-adjusted (singles + voting rules)
first = True
for _, r in pd.concat([singles, kof]).iterrows():
    ax.plot([r.R_cems, r.R_cems], [r.P_cems, r.P_crowd_adj], c="#c9ced4", lw=1.4,
            zorder=1, label="crowd-adjusted precision (top of interval)" if first else None)
    ax.plot(r.R_cems, r.P_crowd_adj, marker="_", ms=9, c="#9aa5b1", zorder=1)
    first = False

ax.scatter(singles.R_cems, singles.P_cems, c="#4a5560", s=80, zorder=4,
           label="single products, as shipped")
offsets = {"UNEP": (-16, -16), "UH": (6, -13), "IMPACT": (5, -16), "OSU": (-34, -16),
           "MS": (7, 1)}
for _, r in singles.iterrows():
    ax.annotate(r.rule, (r.R_cems, r.P_cems), textcoords="offset points",
                xytext=offsets.get(r.rule, (7, -3)), fontsize=10, color="#4a5560")

ax.scatter(pairs.R_cems, pairs.P_cems, facecolors="none", edgecolors="#6b7684", s=70,
           lw=1.4, zorder=3, label="two-product agreement rules")
best = pairs.loc[pairs.P_cems.idxmax()]
ax.annotate(best.rule, (best.R_cems, best.P_cems), textcoords="offset points",
            xytext=(7, 2), fontsize=10, color="#6b7684")

ax.plot(kof.R_cems, kof.P_cems, c="#2a78d6", lw=1.6, zorder=4)
ax.scatter(kof.R_cems, kof.P_cems, c="#2a78d6", s=190, marker="s", zorder=5,
           label="k-of-6 voting rules (k in the square)")
for _, r in kof.iterrows():
    ax.annotate(str(int(r.k)), (r.R_cems, r.P_cems), ha="center", va="center",
                fontsize=10, color="white", zorder=6)

ax.set_xlabel("recall (CEMS {2,3}, scorecard frame: dual-anchor r = 10 m)", fontsize=12)
ax.set_ylabel("precision (CEMS floor, same frame)", fontsize=12)
ax.tick_params(labelsize=11)
ax.set_xlim(0, 0.85)
ax.set_ylim(0, 1.0)
ax.legend(fontsize=10, loc="upper right")
ax.set_title("Six-member voting frontier — every rule's precision is an interval\n"
             "(marker = measured against CEMS; whisker top = crowd-adjusted)", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq5b_frontier_r10.png"), dpi=150)
print("wrote figs/rq5b_frontier_r10.png")
