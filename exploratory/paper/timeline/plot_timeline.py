"""Plot the product release/availability timeline — time on x, product on y.

Reads timeline_events.csv (the source of record; our-ingest dates = UPPER BOUND on
availability, provider release TO CONFIRM). Adds three flagged gaps that postdate that
CSV — UH, LIST (added as evaluation members later, dates unconfirmed) and OSU v1 (the
post-freeze revision, RQ2h) — drawn distinctly so they read as "fill me in", not fact.

Design: one lane per product. Circles = a release/version; a filled star = the FINAL
product actually evaluated (Microsoft's merged union; IMPACT v2). Multi-version products
get a connecting line. Red-outlined "?" markers + a GAPS box = confirm-with-provider.

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/timeline/plot_timeline.py
"""
from __future__ import annotations
import csv, os, sys
from datetime import datetime, timezone, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(__file__)
SLIDES = "--slides" in sys.argv  # deck variant: squarer, larger type, one-line title
MAINSHOCK = datetime(2026, 6, 24, 22, 5, 11, tzinfo=timezone.utc)


def days(iso):
    dt = datetime.strptime(iso.replace("Z", "+0000"), "%Y-%m-%d %H:%M%z")
    return (dt - MAINSHOCK).total_seconds() / 86400


# --- solid events from the CSV, grouped by the product lane ---------------------
rows = list(csv.DictReader(open(os.path.join(HERE, "timeline_events.csv"))))
ev = {}
for r in rows:
    if not r["our_ingest_utc"] or r["source"] in ("overture", "usgs"):
        continue  # pre-event base / context layer
    if r["source"] == "copernicus_ems":
        continue  # replaced below by the real per-AOI schedule
    ev.setdefault(r["source"], []).append((days(r["our_ingest_utc"]), r["milestone"]))


def cems_releases():
    """Copernicus did not publish once — it staggered products per AOI and then issued
    monitoring updates. Reconstruct that from the extents themselves rather than showing a
    single dot. Returns [(days_since_quake, n_products, is_monitoring), ...].

    Caveat: the date available on the extents is the IMAGERY ACQUISITION date, so these are
    a lower bound on publication, whereas every other lane uses our-ingest (an upper bound).
    The lane is annotated accordingly."""
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "artefacts", "lib"))
    import pandas as pd
    import gie_paper as gp  # noqa: E402
    e = gp.cems_extent()
    c = (e[["aoi", "aoi_name", "monitoring_number", "version_number", "acquired"]]
         .drop_duplicates())
    out = {}
    for _, r in c.iterrows():
        ts = pd.to_datetime(r["acquired"], utc=True).to_pydatetime()
        d = (ts - MAINSHOCK).total_seconds() / 86400
        mon = int(r["monitoring_number"]) > 0
        key = (round(d, 3), mon)
        out[key] = out.get(key, 0) + 1
    return sorted((d, n, mon) for (d, mon), n in out.items())

# lane order (bottom→top), label, colour, and role
LANES = [
    ("disha",              "DISHA (UNOPS)",          "#b0b0b0", "excluded (no extent, licence)"),
    ("hot_osm",            "HOT fAIr",               "#b0b0b0", "excluded (no extent)"),
    ("list",               "LIST / WFP / CERN",      "#2e8b57", "evaluated"),
    ("uh",                 "UH QuakeDamage",         "#2e8b57", "evaluated"),
    ("unep_debris",        "UNEP debris",            "#2e8b57", "evaluated"),
    ("osu",                "OSU / NASA",             "#2e8b57", "evaluated"),
    ("impact_initiatives", "IMPACT Initiatives",     "#2e8b57", "evaluated"),
    ("microsoft",          "Microsoft AI4G",         "#2e8b57", "evaluated"),
    ("copernicus_ems",     "Copernicus EMS",         "#1b4f8a", "reference"),
]
yof = {src: i for i, (src, *_ ) in enumerate(LANES)}

# flagged gaps (NOT in the CSV; approximate / to confirm) -----------------------
GAPS = {  # source: (approx_days, label, hard?)
    "uh":   (None, "provider release + our-ingest UNKNOWN — approx? (we promoted to prod ~07-08 → ~13.6 d)"),
    "list": (None, "provider release + our-ingest UNKNOWN — a member by the 07-15 freeze (≤ ~20.7 d)"),
}
OSU_V1_DAYS = days("2026-07-22 00:00Z")  # post-freeze revision (RQ2h)
CEMS = cems_releases()          # real per-AOI + monitoring schedule

fig, ax = plt.subplots(figsize=(10.5, 8) if SLIDES else (13, 7.4))
# The mainshock is an EVENT, so give it a marker on the t=0 line as well as the line itself —
# a bare label beside a rule reads as an axis annotation rather than something that happened.
# The label sits in headroom ABOVE every lane; anchored just above the topmost lane it made
# Copernicus look as though it published at t=0.
EQ_Y = len(LANES) + 0.62
ax.axvline(0, color="#c62828", lw=2, zorder=1)
ax.scatter([0], [EQ_Y], s=260, marker="*", color="#c62828", edgecolor="white", lw=1.2,
           zorder=6, clip_on=False)
ax.text(0.45, EQ_Y, "M7.5 earthquake — 24 Jun 22:05 UTC", color="#c62828",
        fontsize=10.5, va="center", ha="left", weight="bold")

for src, label, col, role in LANES:
    y = yof[src]
    ax.text(-0.35, y, label, ha="right", va="center", fontsize=12,
            weight="bold" if role == "evaluated" else "normal",
            color="#0b0b0b" if role != "excluded" else "#999")
    pts = sorted(ev.get(src, []))
    if pts:
        xs = [d for d, _ in pts]
        if len(xs) > 1:
            ax.plot(xs, [y] * len(xs), color=col, lw=2, alpha=0.5, zorder=2)
        # final version = star (MS union / IMPACT v2 = last point); others = last circle
        for i, (d, m) in enumerate(pts):
            final = (i == len(pts) - 1) and src in ("microsoft", "impact_initiatives")
            ax.scatter(d, y, s=230 if final else 90, marker="*" if final else "o",
                       color=col, edgecolor="white", lw=1, zorder=4)
    # per-lane annotations (short, above/below the lane to avoid collisions)
    if src == "microsoft":
        ax.text(pts[0][0], y + 0.28, "scenes / AOIs →", fontsize=8.5, color="#555", ha="left")
        ax.text(pts[-1][0] + 0.25, y, "union ★ (evaluated)", fontsize=9, color="#2e8b57",
                weight="bold", va="center")
    if src == "impact_initiatives":
        ax.text(pts[0][0], y - 0.32, "v1 raster", fontsize=8.5, color="#555", ha="center")
        ax.text(pts[-1][0] + 0.25, y, "v2 ★ (evaluated)", fontsize=9, color="#2e8b57",
                weight="bold", va="center")
    if src == "osu":
        ax.text(pts[0][0], y - 0.32, "v0 (evaluated)", fontsize=8.5, color="#555", ha="center")
        ax.scatter(OSU_V1_DAYS, y, s=120, marker="D", facecolor="none",
                   edgecolor="#c62828", lw=1.6, zorder=4)
        ax.text(OSU_V1_DAYS, y + 0.3, "v1 revision (07-22)\nnot evaluated — RQ2h", fontsize=8,
                color="#c62828", ha="center")
    if src == "copernicus_ems":
        rel = CEMS
        xs = [d for d, _, _ in rel]
        ax.plot([min(xs), max(xs)], [y, y], color=col, lw=2, alpha=0.45, zorder=2)
        for d, n, mon in rel:
            ax.scatter(d, y, s=70 + 42 * n, marker="s" if mon else "o", color=col,
                       edgecolor="white", lw=1, zorder=4)
            ax.text(d, y + 0.30, f"{n}", fontsize=8.5, color=col, ha="center", weight="bold")
        ax.text(min(xs) - 0.3, y - 0.34, "initial products, per AOI", fontsize=8.5,
                color="#555", ha="left")
        ax.text(max(xs) + 0.55, y, "monitoring updates (squares)", fontsize=8.5, color=col,
                va="center", ha="left")
        ax.text(min(xs) - 0.3, y - 0.62, "dates = imagery acquisition (lower bound on publication)",
                fontsize=7.5, color="#777", ha="left", style="italic")

# flagged unknown-date members (UH, LIST): red "?" out at the right margin
for src, (_, note) in GAPS.items():
    y = yof[src]
    ax.scatter(28.5, y, s=180, marker="$?$", color="#c62828", zorder=4)
    ax.annotate("date TO CONFIRM", (28.5, y), xytext=(28.5, y+0.32), fontsize=8,
                color="#c62828", ha="center")

ax.set_xlim(-3.2, 30)
ax.set_ylim(-0.7, len(LANES) + 0.95)
ax.set_yticks([])
ax.set_xlabel("days since the earthquake  (x = our-ingest date; an UPPER BOUND on availability)"
              if SLIDES else
              "days since the earthquake  (x = our-ingest date; an UPPER BOUND on availability — "
              "provider release is earlier and unconfirmed)", fontsize=11)
# day + date ticks (dates computed directly from clock-zero)
ticks = [0, 2, 4, 6, 8, 14, 21, 28]
ax.set_xticks(ticks)
ax.set_xticklabels([f"{t}\n{(MAINSHOCK + timedelta(days=t)).strftime('%b %-d')}"
                    for t in ticks], fontsize=9)
ax.spines[["top", "right", "left"]].set_visible(False)

leg = [Line2D([], [], marker="o", ls="", color="#2e8b57", label="a release / version"),
       Line2D([], [], marker="*", ls="", color="#2e8b57", ms=12, label="final product evaluated"),
       Line2D([], [], marker="D", ls="", mfc="none", mec="#c62828", label="version not evaluated"),
       Line2D([], [], marker="$?$", ls="", color="#c62828", label="date TO CONFIRM (gap)")]
ax.legend(handles=leg, loc="lower right", fontsize=9.5, frameon=True)
ax.set_title("When each damage product became available" if SLIDES else
             "When each damage product became available — VE earthquake\n"
             "the ecosystem arrived inside ~8 days; Microsoft delivered scene-by-scene → a "
             "merged union; IMPACT & OSU each had two versions", fontsize=12)
if SLIDES:
    for t in fig.findobj(matplotlib.text.Text):
        t.set_fontsize(t.get_fontsize() * 1.35)
fig.tight_layout()
out = os.path.join(HERE, f"timeline_products{'_slides' if SLIDES else ''}.png")
fig.savefig(out, dpi=150)
print(f"wrote {out}")
print("\nGAPS to fill (flagged on the plot):")
print("  - UH QuakeDamage: provider release + our-ingest date UNKNOWN")
print("  - LIST/WFP/CERN: provider release + our-ingest date UNKNOWN (member by 07-15 freeze)")
print("  - OSU v1 (07-22) date shown but not evaluated; confirm exact provider date")
print("  - ALL provider-release dates TO CONFIRM (x = our upper-bound ingest)")
