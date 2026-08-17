"""Figure: does the crowd adjudicate Microsoft's west-Caraballeda over-detection cluster?

FIGURE-ONLY — reads the frozen `rq7_west_cluster_join.csv` (88 H3 res-8 cells, 3,771 crowd
tasks) and takes seconds. The parent script `rq7_west_cluster.py` does the data pull and the
statistics, but it reads MapSwipe from a session scratchpad that no longer exists, so it
cannot currently be re-run; this rebuilds the figure from its committed output instead.

WHY THIS SCRIPT EXISTS. The earlier version of this figure showed two maps under the title
"The over-flagged western cluster is EXACTLY where volunteers saw no damage". That asserts a
cell-by-cell spatial coincidence, and at cell scale there isn't one: rho = +0.09, p = 0.39
(NOTES.md records the same null). The scatter panel that showed this had been dropped from
the figure as "confusing", which left two maps making a claim the analysis did not support.

The finding is real, but it lives at STRIP scale, not cell scale: across the western strip
volunteers rejected 71% of Microsoft's flags, against a roughly even split in the damage-dense
east. So all three panels are drawn: the two maps (which do show the macro gradient) and the
scatter (which shows the cell-scale relationship is flat), with the scale of the claim stated
in the title rather than left to the caption.

Run: uv run --with pandas --with scipy --with matplotlib --with h3 --with contextily python \
       exploratory/paper/artefacts/RQ7-mapswipe-validation/scripts/rq7_west_cluster_fig.py
"""
from __future__ import annotations
import os

import h3
import matplotlib
import numpy as np
import pandas as pd
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

HERE = os.path.dirname(__file__)
CSV = os.path.join(HERE, "..", "rq7_west_cluster_join.csv")
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

# Strip-scale result from rq7_west_cluster.py / NOTES.md — the evidence the slide rests on.
WEST_REJECT, EAST_REJECT, EAST_CONFIRM = 0.71, 0.49, 0.48


def main() -> None:
    import contextily as cx

    j = pd.read_csv(CSV)
    ll = np.array([h3.cell_to_latlng(c) for c in j.parent8])
    # project to Web Mercator so the map panels can carry a tile basemap (review request)
    mx = ll[:, 1] * 20037508.34 / 180.0
    my = np.log(np.tan((90.0 + ll[:, 0]) * np.pi / 360.0)) / (np.pi / 180.0) * 20037508.34 / 180.0
    rho, p = spearmanr(j.resid, j.rej_share)
    print(f"{len(j)} cells, {int(j.n_tasks.sum()):,} tasks | "
          f"rho(residual, rejection) = {rho:+.3f} (p={p:.2f})")

    # The mapped area is a wide, short coastal strip, so the two maps stack in a narrow
    # left column and the scatter takes a square panel on the right.
    fig = plt.figure(figsize=(17, 5.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1], height_ratios=[1, 1],
                          hspace=0.45, wspace=0.18)
    ax_res, ax_crowd = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0])
    ax_sc = fig.add_subplot(gs[:, 1])

    lim = np.percentile(np.abs(j.resid), 98)
    s0 = ax_res.scatter(mx, my, c=j.resid, cmap="RdBu_r",
                        vmin=-lim, vmax=lim, s=70, edgecolor="white", linewidth=0.4)
    ax_res.set_title("Where Microsoft over-flags  (red = flags far beyond real damage)",
                     fontsize=12)
    plt.colorbar(s0, ax=ax_res, shrink=0.92, pad=0.015, label="over-detection")

    s1 = ax_crowd.scatter(mx, my, c=j.rej_share, cmap="PuOr_r",
                          vmin=0, vmax=1, s=70, edgecolor="white", linewidth=0.4)
    ax_crowd.set_title("What MapSwipe volunteers said  (orange = 'no damage here')",
                       fontsize=12)
    plt.colorbar(s1, ax=ax_crowd, shrink=0.92, pad=0.015, label="share voting 'no damage'")

    for a in (ax_res, ax_crowd):
        a.set_aspect("equal")
        a.set_xticks([])
        a.set_yticks([])
        cx.add_basemap(a, source=cx.providers.CartoDB.Positron, crs="EPSG:3857",
                       attribution_size=5)

    # Right panel: the relationship the two maps are often read as implying. It is flat.
    ax_sc.scatter(j.resid, j.rej_share, s=46, c="#5a6570", alpha=0.72, edgecolor="none")
    ax_sc.axhline(j.rej_share.mean(), color="#e34948", lw=1.4, ls="--",
                  label=f"mean rejection {j.rej_share.mean():.2f}")
    ax_sc.set_xlabel("Microsoft over-detection (cell residual)", fontsize=11)
    ax_sc.set_ylabel("share voting 'no damage'", fontsize=11)
    ax_sc.set_title(f"Cell by cell, the two do NOT track\n"
                    r"Spearman $\rho$ = " f"{rho:+.2f} (p = {p:.2f}), n = {len(j)} cells",
                    fontsize=13)
    ax_sc.set_ylim(0, 1)
    ax_sc.legend(fontsize=9, loc="upper right", frameon=False)
    for side in ("top", "right"):
        ax_sc.spines[side].set_visible(False)

    fig.suptitle(
        "The crowd rejects Microsoft's western flags at STRIP scale — not cell by cell: "
        f"{WEST_REJECT:.0%} of west-strip flags judged 'no damage', "
        f"vs {EAST_REJECT:.0%}/{EAST_CONFIRM:.0%} no/yes in the east",
        fontsize=14, weight="bold")
    fig.subplots_adjust(top=0.86, left=0.02, right=0.97, bottom=0.11)
    out = os.path.join(FIGS, "rq7_west_cluster_adjudication.png")
    fig.savefig(out, dpi=140)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
