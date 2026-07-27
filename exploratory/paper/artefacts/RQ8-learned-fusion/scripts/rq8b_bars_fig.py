"""RQ8b deck bar chart — as-delivered: each product's AP vs the day-zero baseline.

Wide, large-font, slide-legible. Reads rq8b_asdelivered_baseline.csv only (no compute).
Shows the headline: as delivered, 5 of 6 products carry less building-level information
(average precision) than a no-satellite day-zero model on the same footprint.

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8b_bars_fig.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
df = pd.read_csv(os.path.join(HERE, "..", "rq8b_asdelivered_baseline.csv"))
df = df.sort_values("AP_product")

y = np.arange(len(df))
fig, ax = plt.subplots(figsize=(13, 6.5))
h = 0.38
ax.barh(y + h/2, df.AP_dayzero, height=h, color="#e34948",
        label="day-zero baseline  (coast + density + ShakeMap, no satellite)")
ax.barh(y - h/2, df.AP_product, height=h, color="#4a5560",
        label="the satellite product, as delivered")
for yi, (_, r) in zip(y, df.iterrows()):
    ax.text(r.AP_product + 0.002, yi - h/2, f"{r.AP_product:.3f}", va="center",
            fontsize=12, color="#4a5560")
    ax.text(r.AP_dayzero + 0.002, yi + h/2, f"{r.AP_dayzero:.3f}", va="center",
            fontsize=12, color="#c62828")
    win = "beats baseline" if r.AP_product >= r.AP_dayzero else "loses to baseline"
    ax.text(-0.004, yi, r["product"], va="center", ha="right", fontsize=14,
            weight="bold", color="#0b0b0b")

ax.set_yticks([])
ax.set_xlim(0, max(df.AP_dayzero.max(), df.AP_product.max()) * 1.18)
ax.set_xlabel("average precision, as delivered  (spatial-block CV; higher = better)",
              fontsize=14)
ax.tick_params(axis="x", labelsize=12)
ax.legend(fontsize=13, loc="lower right", frameon=True)
ax.set_title("As delivered, five of six products carry less information than "
             "a no-satellite baseline\n"
             "(Microsoft is the exception — because it only shipped its analysed strip)",
             fontsize=14.5)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq8b_asdelivered_bars.png"), dpi=150)
print("wrote rq8b_asdelivered_bars.png")
