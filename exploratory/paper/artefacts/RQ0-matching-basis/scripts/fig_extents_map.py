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

    fig, axs = plt.subplots(2, 1, figsize=(15, 11.6),
                            gridspec_kw={"height_ratios": [1.55, 1], "hspace": 0.14})
    for a in axs:
        a.set_facecolor("#dcebf5")
    # Two stacked frames (user feedback 2026-08-06: the inset obscured the overview, and
    # six translucent fills went muddy). Extents are now near-transparent fills with
    # strong distinct outlines, and the core-region zoom is its own bottom frame.
    def extents(ax, lw_scale=1.0):
        draw(ax, land, fc="#f4f3ee", ec="#b9b7ae", lw=0.8, z=0)
        for nm, a in aois.items():
            draw(ax, a, fc=COL[nm], ec="none", alpha=0.045, z=1)
            draw(ax, a, ec=COL[nm], lw=1.9 * lw_scale, z=3)
        draw(ax, cems_u, ec="#1b1f24", lw=1.4 * lw_scale, ls="--", z=4)
        draw(ax, core, fc=CORE, ec=CORE, lw=1.0, alpha=0.85, z=5)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])

    ax, axz = axs
    extents(ax)

    # label the CEMS AOIs from their own geometry; per-AOI nudges keep the two
    # neighbouring capital-area labels (Caraballeda coast / Caracas inland) apart
    NUDGE = {"Caracas": (0, -26), "Caraballeda": (0, 16)}
    for _, row in cems.dissolve("aoi_name").reset_index().iterrows():
        c = row.geometry.representative_point()
        ax.annotate(row.aoi_name, (c.x, c.y), fontsize=10.5, weight="bold",
                    color="#1b1f24", ha="center",
                    xytext=NUDGE.get(row.aoi_name, (0, 14)),
                    textcoords="offset points", zorder=8)

    # Frame on everything EXCEPT LIST: its two full Sentinel scenes (~224,000 km²) would
    # force a square frame that shrinks the coast to a sliver. LIST bleeds off-frame and
    # an annotation says so — the legend carries its true area.
    minx, miny, maxx, maxy = gpd.GeoSeries(
        [cems_u, *(a for nm, a in aois.items() if nm != "LIST")],
        crs=gp.METRIC_CRS).total_bounds
    padx, pady = (maxx - minx) * 0.05, (maxy - miny) * 0.14
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.annotate("LIST extent continues ~300 km south + west (223,708 km²) →",
                xy=(0.015, 0.03), xycoords="axes fraction", fontsize=9.5,
                color=COL["LIST"], style="italic", zorder=8)

    # bottom frame: the Caraballeda coastal strip, where the core region actually lives
    cminx, cminy, cmaxx, cmaxy = gpd.GeoSeries([core], crs=gp.METRIC_CRS).total_bounds
    ipx, ipy = (cmaxx - cminx) * 0.16, (cmaxy - cminy) * 0.85
    extents(axz, lw_scale=0.8)
    axz.set_xlim(cminx - ipx, cmaxx + ipx)
    axz.set_ylim(cminy - ipy, cmaxy + ipy)
    axz.set_title(f"zoom: the core region — every extent at once "
                  f"({core.area / 1e6:,.0f} km²)", fontsize=11.5, color=CORE, weight="bold")
    for s in axz.spines.values():
        s.set_edgecolor(CORE)
        s.set_linewidth(1.4)
    ax.add_patch(Rectangle((cminx - ipx, cminy - ipy), (cmaxx - cminx) + 2 * ipx,
                           (cmaxy - cminy) + 2 * ipy, fill=False, ec=CORE, lw=1.4, zorder=7))

    handles = [Line2D([], [], color=COL[nm], lw=2.2,
                      label=f"{nm} analysed extent ({aois[nm].area / 1e6:,.0f} km²)"
                            + (" — derived from its footprints" if nm == "UH" else ""))
               for nm in aois]
    handles += [Line2D([], [], color="#1b1f24", ls="--", lw=1.4,
                       label="CEMS expert-mapped AOIs (the reference)"),
                Patch(facecolor=CORE, alpha=0.85,
                      label=f"core region = CEMS ∩ all five ({core.area / 1e6:,.0f} km²)")]
    ax.legend(handles=handles, loc="upper left", fontsize=9.5, framealpha=0.95)
    ax.set_title("Who analysed where — six products, one shared yardstick area",
                 fontsize=14.5, weight="bold")
    fig.text(0.5, 0.045,
             "UNEP debris publishes no analysed extent and is not drawn: the analysis assumes "
             "it covers the core region (see Methods).\nScoring happens only where a product "
             "and the reference both looked.",
             ha="center", fontsize=9.5, color="#5a6570", va="top")

    out = os.path.join(FIGS, "fig_extents_map.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
