"""Map of who analysed where: the six products' extents, the CEMS AOIs, and the core region.

Every scored number in the paper lives inside some intersection of these polygons, and the
text talks about them constantly ("core region", "as delivered", "96% of the reference sits
in one AOI") without ever showing them. One figure: each product's analysed extent, the five
CEMS AOIs it can be scored against, and the five-way core intersection (~61 km²) where the
ensemble/fusion analyses live — plus an inset zoom on the Caraballeda strip, since at national
scale the core region is a sliver.

Notes recorded on the figure itself, because they are easy to forget:
- UH publishes no extent; its polygon here is DERIVED from its own classified footprints
  (res-9 cells + one-ring dilation, ADR-0018) — self-referential by construction.
- UNEP debris publishes no extent at all and is drawn nowhere; the analysis assumes it
  covers the core region (stated in Methods).

Run: uv run --group etl --with matplotlib python \
       exploratory/paper/artefacts/RQ0-matching-basis/scripts/fig_extents_map.py
"""
from __future__ import annotations
import os, sys

import geopandas as gpd
import h3
import matplotlib
import numpy as np
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

COL = {"Microsoft": "#2a78d6", "IMPACT v2": "#8a5cd6", "OSU": "#1b9e77",
       "UH": "#e6a817", "LIST": "#d95f02"}
CORE = "#c62828"


def uh_aoi():
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def main() -> None:
    aois = {
        "Microsoft": gp.dissolve_union(gp.microsoft_aoi()),
        "IMPACT v2": gp.dissolve_union(gp.impact_v2_aoi()),
        "OSU": gp.dissolve_union(gp.osu_aoi()),
        "UH": uh_aoi(),
        "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                              "analysed_extent.parquet")),
    }
    cems = gp.to_metric(gp.cems_extent().query("is_latest"))
    cems_u = cems.geometry.make_valid().union_all()

    core = cems_u
    for a in aois.values():
        core = core.intersection(a)

    land = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all()

    print(f"{'extent':12} {'km²':>10}")
    for nm, a in aois.items():
        print(f"{nm:12} {a.area / 1e6:10,.0f}")
    print(f"{'CEMS (all)':12} {cems_u.area / 1e6:10,.0f}")
    print(f"{'CORE ∩':12} {core.area / 1e6:10,.0f}")

    def draw(ax, geom, *, fc="none", ec="k", lw=1.0, alpha=1.0, ls="-", hatch=None, z=2):
        for g in getattr(geom, "geoms", [geom]):
            if g.is_empty or not hasattr(g, "exterior"):
                continue
            ax.fill(*g.exterior.xy, facecolor=fc, edgecolor=ec, lw=lw,
                    alpha=alpha, ls=ls, hatch=hatch, zorder=z)

    fig, ax = plt.subplots(figsize=(15, 8.2))
    ax.set_facecolor("#dcebf5")
    draw(ax, land, fc="#f4f3ee", ec="#b9b7ae", lw=0.8, z=0)
    for nm, a in aois.items():
        # one pass: filled at low alpha with a modest outline, so OSU's thin scene
        # strips read as context rather than dominating the frame
        draw(ax, a, fc=COL[nm], ec=COL[nm], lw=1.0, alpha=0.16, z=2)
    draw(ax, cems_u, ec="#1b1f24", lw=1.3, ls="--", z=4)
    draw(ax, core, fc=CORE, ec=CORE, lw=1.2, alpha=0.85, z=5)

    # label the CEMS AOIs from their own geometry; per-AOI nudges keep the two
    # neighbouring capital-area labels (Caraballeda coast / Caracas inland) apart
    NUDGE = {"Caracas": (0, -26), "Caraballeda": (0, 16)}
    for _, row in cems.dissolve("aoi_name").reset_index().iterrows():
        c = row.geometry.representative_point()
        ax.annotate(row.aoi_name, (c.x, c.y), fontsize=10.5, weight="bold",
                    color="#1b1f24", ha="center",
                    xytext=NUDGE.get(row.aoi_name, (0, 14)),
                    textcoords="offset points", zorder=8)

    # frame the whole scene
    minx, miny, maxx, maxy = gpd.GeoSeries(
        [cems_u, *aois.values()], crs=gp.METRIC_CRS).total_bounds
    padx, pady = (maxx - minx) * 0.04, (maxy - miny) * 0.10
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])

    # inset: the Caraballeda coastal strip, where the core region actually lives
    cminx, cminy, cmaxx, cmaxy = gpd.GeoSeries([core], crs=gp.METRIC_CRS).total_bounds
    ipx, ipy = (cmaxx - cminx) * 0.18, (cmaxy - cminy) * 0.55
    axi = ax.inset_axes([0.40, 0.05, 0.585, 0.34])
    axi.set_facecolor("#dcebf5")
    draw(axi, land, fc="#f4f3ee", ec="#b9b7ae", lw=0.8, z=0)
    for nm, a in aois.items():
        draw(axi, a, fc=COL[nm], ec=COL[nm], lw=1.2, alpha=0.14, z=2)
    draw(axi, cems_u, ec="#1b1f24", lw=1.1, ls="--", z=4)
    draw(axi, core, fc=CORE, ec=CORE, lw=1.0, alpha=0.85, z=5)
    axi.set_xlim(cminx - ipx, cmaxx + ipx)
    axi.set_ylim(cminy - ipy, cmaxy + ipy)
    axi.set_aspect("equal")
    axi.set_xticks([])
    axi.set_yticks([])
    axi.set_title(f"the core region — every extent at once ({core.area / 1e6:,.0f} km²)",
                  fontsize=10.5, color=CORE, weight="bold")
    for s in axi.spines.values():
        s.set_edgecolor(CORE)
        s.set_linewidth(1.4)
    ax.add_patch(Rectangle((cminx - ipx, cminy - ipy), (cmaxx - cminx) + 2 * ipx,
                           (cmaxy - cminy) + 2 * ipy, fill=False, ec=CORE, lw=1.2, zorder=7))

    handles = [Patch(facecolor=COL[nm], edgecolor=COL[nm], alpha=0.45,
                     label=f"{nm} analysed extent ({aois[nm].area / 1e6:,.0f} km²)"
                           + (" — derived from its footprints" if nm == "UH" else ""))
               for nm in aois]
    handles += [Line2D([], [], color="#1b1f24", ls="--", lw=1.3,
                       label="CEMS expert-mapped AOIs (the reference)"),
                Patch(facecolor=CORE, alpha=0.85,
                      label=f"core region = CEMS ∩ all five ({core.area / 1e6:,.0f} km²)")]
    ax.legend(handles=handles, loc="upper left", fontsize=9.5, framealpha=0.95)
    ax.set_title("Who analysed where — six products, one shared yardstick area",
                 fontsize=14.5, weight="bold")
    ax.text(0.005, -0.02,
            "UNEP debris publishes no analysed extent and is not drawn: the analysis assumes "
            "it covers the core region (see Methods). Scoring happens only where a product "
            "and the reference both looked.",
            transform=ax.transAxes, fontsize=9, color="#5a6570", va="top")

    fig.tight_layout()
    out = os.path.join(FIGS, "fig_extents_map.png")
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
