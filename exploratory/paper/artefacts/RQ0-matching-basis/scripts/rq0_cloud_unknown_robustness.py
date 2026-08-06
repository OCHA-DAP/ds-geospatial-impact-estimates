"""RQ0 robustness — does MS per-building cloud/no-data fraction (unknown_pct) bias our scores?

Microsoft's merged bronze file carries `unknown_pct` (fraction of the building buffer that
was cloud/no-data in the imagery). Our harmonize drops the column and the valid-area mask
does NOT excise cloud holes (99%+ of high-unknown buildings sit inside it), so no scoring
step ever accounted for cloud. This script quantifies whether that matters, in the exact
rq5b core-region frame (CEMS latest extent ∩ 5 product AOIs):

  A. distribution of unknown_pct (overall / flagged / by num_observations)
  B. does the valid-area mask already exclude high-unknown buildings? (no)
  C. precision with/without a visibility filter on flags
  D. recall over CEMS points restricted to visibly-analysed stock

Frozen-batch result (2026-07-20): NEGLIGIBLE. 3.6% of buildings majority-obscured;
P 0.089 unchanged at any threshold; 1/794 missed CEMS points on obscured stock; cloud is
concentrated in intact multi-scene east areas — the single-scene west FP cluster is the
most cloud-free zone (2.8% vs 5.2% obscured).

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ0-matching-basis/scripts/rq0_cloud_unknown_robustness.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from shapely.geometry import Polygon
from shapely.ops import unary_union
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
R = 10


def _bronze(name):
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    blob = gp.S.blob_path("bronze", "source=microsoft", "adm0=VE", "merged", name)
    return gpd.read_file(io.BytesIO(cc.download_blob(blob).readall()))


def uh_aoi():
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def main():
    m = _bronze("ALL_AOIS_building_predictions_deduplicated.gpkg").to_crs(gp.METRIC_CRS)
    u = m.unknown_pct.astype(float)
    print(f"n={len(m):,} | unknown_pct mean {u.mean():.3f} | >0.5: {(u > 0.5).mean():.1%} "
          f"(flagged {(u[m.damaged == 1] > 0.5).mean():.1%} / "
          f"intact {(u[m.damaged == 0] > 0.5).mean():.1%})")
    obs = {int(k): round(float((sub > 0.5).mean()), 3)
           for k, sub in u.groupby(m.num_observations)}
    print(f"share obscured (>0.5) by num_observations: {obs}")

    mask = _bronze("valid_area_mask_union.geojson").to_crs(gp.METRIC_CRS)
    hi = m[u > 0.5]
    in_mask = hi.geometry.representative_point().within(mask.geometry.make_valid().union_all())
    print(f"high-unknown buildings inside valid mask: {in_mask.mean():.1%} "
          f"(mask does NOT excise cloud)")

    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    rep = m.geometry.representative_point()
    m["x"], m["y"] = rep.x, rep.y
    in_reg = rep.within(region)
    cems = gp.to_metric(gp.cems_points())
    cpts = cems[cems.damage_class.isin(POS)][["geometry"]]
    cpts = cpts[cpts.geometry.within(region)]

    fl = m[in_reg & (m.damaged == 1)]
    ct = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
    hit = ct.query(np.c_[fl.x, fl.y], k=1)[0] <= R
    mr = m[in_reg]
    d_b, i_b = cKDTree(np.c_[mr.x, mr.y]).query(np.c_[cpts.geometry.x, cpts.geometry.y], k=1)
    on_stock = d_b <= 15
    uu = mr.unknown_pct.to_numpy()[i_b]
    matched = cKDTree(np.c_[fl.x, fl.y]).query(
        np.c_[cpts.geometry.x, cpts.geometry.y], k=1)[0] <= R

    rows = []
    for t in (None, 0.5, 0.25):
        keep = np.ones(len(fl), bool) if t is None else (fl.unknown_pct <= t).to_numpy()
        vis = on_stock if t is None else (on_stock & (uu <= t))
        rows.append(dict(
            threshold="none" if t is None else t,
            P=round(float(hit[keep].mean()), 3), flags_kept=int(keep.sum()),
            R=round(float(matched[vis].mean() if t is not None else matched.mean()), 3),
            cems_pts_kept=int(vis.sum() if t is not None else len(cpts)),
            missed_on_obscured=int((on_stock & ~matched & (uu > (t or 1.0))).sum())))
        print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq0_cloud_unknown_robustness.csv"), index=False)
    print("wrote rq0_cloud_unknown_robustness.csv")


if __name__ == "__main__":
    main()
