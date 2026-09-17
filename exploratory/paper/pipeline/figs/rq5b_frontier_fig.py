"""RQ5b frontier figure — six members, scorecard frame (dual-anchor r=10 m).

Replaces the stale four-member rq5_pr_frontier_r10.png in the manuscript. Reads the
frozen rq5b_six_member.csv only (no blob access). Styling matches the day-zero baseline
figure: grey dots = shipped products, numbered blue squares = k-of-6 voting rules.
Vertical whiskers show each rule's precision interval: CEMS-measured floor (marker) up
to crowd-adjusted precision (tick).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/pipeline/figs/rq5b_frontier_fig.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "..", "figures")
os.makedirs(FIGS, exist_ok=True)

df = pd.read_csv(os.path.join(HERE, "..", "legacy", "rq5b_six_member.csv"))
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
    ax.plot([r.R_cems, r.R_cems], [r.P_cems, r.P_crowd], c="#c9ced4", lw=1.4,
            zorder=1, label="crowd-adjusted precision (top of interval)" if first else None)
    ax.plot(r.R_cems, r.P_crowd, marker="_", ms=9, c="#9aa5b1", zorder=1)
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
# label every pair (all 15 are drawn). Labels start beside their marker and are pushed apart
# from each other and from every other marker (singles, k-squares) in axes coordinates, then
# joined to their marker by a hairline where they had to move.
import numpy as np
xmax = max(1.0, float(df.R_cems.max()) + 0.05)
def to_ax(x, y): return np.array([x / xmax, y / 1.0])
obstacles = [to_ax(r.R_cems, r.P_cems) for _, r in pd.concat([singles, kof]).iterrows()]
lab = pairs.reset_index(drop=True)
pos = np.array([to_ax(r.R_cems, r.P_cems) + np.array([0.012, 0.012]) for _, r in lab.iterrows()])
anchors = np.array([to_ax(r.R_cems, r.P_cems) for _, r in lab.iterrows()])
# labels are wide and short, so clearance is elliptical: ~0.11 of the axes wide, ~0.035 tall
SCALE = np.array([0.11, 0.035])
def push(i, other, factor=1.0):
    d = (pos[i] - other) / (SCALE * factor); n = np.linalg.norm(d)
    if n < 1.0:
        pos[i] += (d / (n + 1e-9)) * (1.0 - n) * 0.5 * SCALE * factor
        return True
    return False
for _ in range(600):
    moved = False
    for i in range(len(pos)):
        for j in range(len(pos)):
            if i != j:
                moved |= push(i, pos[j])
        for o in obstacles + [a for k, a in enumerate(anchors) if k != i]:
            moved |= push(i, o, 0.7)
        pos[i] = np.clip(pos[i], 0.04, 0.96)
    if not moved:
        break
for i, r in lab.iterrows():
    ax.annotate(r.rule, xy=(r.R_cems, r.P_cems), xytext=(pos[i][0], pos[i][1]), textcoords="axes fraction",
                fontsize=8, color="#6b7684", ha="center", va="center",
                arrowprops=dict(arrowstyle="-", lw=0.5, color="#b0b7bf", shrinkA=0, shrinkB=4))

ax.plot(kof.R_cems, kof.P_cems, c="#2a78d6", lw=1.6, zorder=4)
ax.scatter(kof.R_cems, kof.P_cems, c="#2a78d6", s=190, marker="s", zorder=5,
           label="k-of-6 voting rules (k in the square)")
for _, r in kof.iterrows():
    ax.annotate(str(int(r.k)), (r.R_cems, r.P_cems), ha="center", va="center",
                fontsize=10, color="white", zorder=6)

ax.set_xlabel("recall (CEMS {2,3}, core region, r = 10 m)", fontsize=12)
ax.set_ylabel("precision (CEMS floor, same frame)", fontsize=12)
ax.tick_params(labelsize=11)
ax.set_xlim(0, max(1.0, float(df.R_cems.max()) + 0.05))   # data-driven: a fixed 0.85 once clipped 1-of-6 and 2-of-6 (recall .95, .90)
ax.set_ylim(0, 1.0)
ax.legend(fontsize=10, loc="upper right")
ax.set_title("Six-member voting frontier — every rule's precision is an interval\n"
             "(marker = measured against CEMS; whisker top = crowd-adjusted)", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq5b_frontier_r10.png"), dpi=150)
print("wrote figures/rq5b_frontier_r10.png")
