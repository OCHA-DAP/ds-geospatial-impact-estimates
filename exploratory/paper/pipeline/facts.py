"""Facts the brief states about the study's geography and inputs, computed rather than typed:
region areas and building counts, reference points per AOI and grade, the LIST-extent
shares, building spacing, H3 cell areas, Microsoft's cloud-obscured share, OSU v0/v1 totals,
field-report counts. Rows of the results table with lens = "facts".

Usage: python facts.py -> results_facts.csv beside this file
"""
from __future__ import annotations

import io
import os
import sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as pl  # noqa: E402
from paperlib import gp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = "pipeline/facts.py"


def rows(region, predictor, **metrics):
    return [dict(region=region, lens="facts", radius=np.nan, predictor=predictor, metric=m, value=float(v), source=SOURCE)
            for m, v in metrics.items() if v is not None and not (isinstance(v, float) and np.isnan(v))]


def regions() -> list:
    b, core = pl.buildings(), pl.core_region()
    inb = b[pl.in_region(b, core)]
    aois = pl.product_aois()
    overlap = None
    for a in aois.values():
        overlap = a if overlap is None else overlap.intersection(a)
    out = rows("core", "region", area_km2=core.area / 1e6, n_buildings=len(inb))
    out += rows("all", "region", products_overlap_km2=overlap.area / 1e6, cems_extent_km2=pl.cems_extent_latest().area / 1e6,
                n_buildings_base=len(b))
    for p, a in aois.items():
        out += rows("all", p, aoi_km2=a.area / 1e6)
    # building spacing in the core (centroid nearest neighbour)
    xy = np.c_[inb.geometry.centroid.x, inb.geometry.centroid.y]
    d, _ = cKDTree(xy).query(xy, k=2)
    nn = d[:, 1]
    out += rows("core", "spacing", median_nn_m=float(np.median(nn)), share_nn_within_20m=float((nn <= 20).mean()), share_nn_within_10m=float((nn <= 10).mean()))
    return out


def reference_points() -> list:
    cems = gp.to_metric(gp.cems_points())
    core = pl.core_region()
    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    out = []
    pos = cems[cems.damage_class.isin((2, 3))]
    out += rows("all", "CEMS", n_points_all_grades=len(cems), n_points_2_3=len(pos), n_points_1=int((cems.damage_class == 1).sum()))
    core_pts = cems[cems.geometry.within(core)]
    out += rows("core", "CEMS", n_points_2_3=int(core_pts.damage_class.isin((2, 3)).sum()), n_destroyed=int((core_pts.damage_class == 3).sum()),
                n_damaged=int((core_pts.damage_class == 2).sum()), n_possibly=int((core_pts.damage_class == 1).sum()))
    for aoi, sub in ext.groupby("aoi_name"):
        reg = sub.geometry.make_valid().union_all()
        n = int(pos.geometry.within(reg).sum())
        out += rows(aoi, "CEMS", n_points_2_3=n, share_of_points_2_3=n / len(pos))
    return out


def h3_areas() -> list:
    return sum((rows("all", f"h3-res{r}", avg_area_km2=h3.average_hexagon_area(r, unit="km^2")) for r in (7, 8, 9, 11, 12)), [])


def microsoft_cloud() -> list:
    """Share of Microsoft-analysed footprints in the core that are mostly obscured (unknown_pct > 0.5)."""
    import ocha_stratus as stratus
    import tempfile
    blob = gp.S.blob_path("bronze", "source=microsoft", "adm0=VE", "merged", "ALL_AOIS_building_predictions_deduplicated.gpkg", event=None)
    with tempfile.NamedTemporaryFile(suffix=".gpkg") as f:
        f.write(stratus.load_blob_data(blob, stage="dev", container_name=gp.S.container)); f.flush()
        ms = gpd.read_file(f.name).to_crs(pl.METRIC_CRS)
    core = pl.core_region()
    inc = ms[ms.geometry.representative_point().within(core)]
    return (rows("all", "MS", n_footprints=len(ms), share_mostly_obscured=float((ms.unknown_pct > 0.5).mean()))
            + rows("core", "MS", n_footprints=len(inc), share_mostly_obscured=float((inc.unknown_pct > 0.5).mean())))


def disha_extent() -> list:
    """DISHA's analysed extent (licence-gated points are never used): how much of the core it
    covers and how many reference points it holds — why it is not a comparison member."""
    ext = gp.dissolve_union(gp._read_pq("silver", "source=disha", "adm0=VE", "analysed_extent.parquet"))
    core = pl.core_region()
    ref = pl.reference("floor"); in_core = ref[ref.geometry.within(core)]
    return rows("core", "DISHA", extent_km2=ext.area / 1e6, covers_km2=ext.intersection(core).area / 1e6,
                share_of_core=ext.intersection(core).area / core.area,
                cems_in_extent=int(in_core.geometry.within(ext).sum()), cems_in_core=len(in_core))


def osu_versions() -> list:
    """OSU v0 vs v1 delivered flags, and the turnover between them on the shared base."""
    import ocha_stratus as stratus
    ids, sat = {}, np.nan
    for v in ("v0", "v1"):
        raw = stratus.load_blob_data(gp.S.blob_path("silver", "source=osu", "adm0=VE", f"version={v}", "building_damage.parquet", event=None),
                                     stage="dev", container_name=gp.S.container)
        d = pd.read_parquet(io.BytesIO(raw))
        ids[v] = set(d.id)
        if v == "v0":
            sat = float((d.damage_probability == 1.0).mean())   # v0's score saturation
    base = set(pl.buildings().id)
    v0, v1 = ids["v0"] & base, ids["v1"] & base
    return rows("all", "OSU", v0_flags_delivered=len(ids["v0"]), v1_flags_delivered=len(ids["v1"]), v0_flags_on_base=len(v0), v1_flags_on_base=len(v1),
                dropped_v0_to_v1=len(v0 - v1), added_v0_to_v1=len(v1 - v0), coverage_growth=len(ids["v1"]) / len(ids["v0"]) - 1,
                v0_share_probability_1=sat)


def footprint_maps() -> list:
    """How each own-footprint product's delivery maps onto the shared base (lib/footprint_map_manifest.csv)."""
    m = pd.read_csv(os.path.join(HERE, "..", "lib", "footprint_map_manifest.csv")).set_index("product")
    out = []
    for key, p in (("ms", "MS"), ("unep", "UNEP"), ("uh", "UH")):
        r = m.loc[key]
        out += rows("all", p, delivered_footprints=r.delivered, mapped_by_iou=r.mapped_by_iou, mapped_by_snap=r.mapped_by_snap,
                    orphans=r.orphans, base_buildings=r.base_ids, collapsed=r.collapsed, median_iou=r.median_iou)
    return out


def field() -> list:
    f = pl.field_points()
    out = rows("all", "ChatMap", n_points=len(f))
    for gr, n in f.damaged.value_counts().items():
        out += rows("all", "ChatMap", **{f"n_{gr}": int(n)})
    return out


def main():
    out = []
    for fn in (regions, reference_points, h3_areas, microsoft_cloud, disha_extent, osu_versions, footprint_maps, field):
        print(f"== {fn.__name__}", flush=True)
        out += fn()
    res = pd.DataFrame(out)
    res.to_csv(os.path.join(HERE, "results_facts.csv"), index=False)
    print(f"results_facts.csv: {len(res)} rows")
    print(res[["region", "predictor", "metric", "value"]].to_string())


if __name__ == "__main__":
    main()
