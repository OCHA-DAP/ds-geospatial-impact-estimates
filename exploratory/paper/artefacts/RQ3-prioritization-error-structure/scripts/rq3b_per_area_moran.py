"""RQ3b addendum — Moran's I per CEMS analysed area, per product, and pooled.

The headline RQ3b Moran's I was computed over each product's WHOLE shared region (CEMS ∩
product AOI) — for IMPACT/OSU/UH that pools several disjoint CEMS areas. Here: same
exposure-spec GLM + permutation Moran's I, split by CEMS aoi_name and pooled ("ALL"),
members MS / IMPACT v2 / OSU / UH.

Basis note: flags from gold building_flags (Overture centroids — same construction basis as
RQ5/RQ2c, NOT the native-footprint basis of the original rq3_error_structure.py; I values are
comparable within this table, and approximately with the originals). In near-zero-damage areas
(Caracas, Santa Cruz: ~3 CEMS pts) the GLM is ≈ intercept-only, so Moran's I there reads as
"do FALSE-POSITIVE rate deviations clump?" — exactly the negative-control question.

Run: uv run --group etl --with statsmodels --with scipy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3b_per_area_moran.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import statsmodels.api as sm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

POS = (2, 3)
RES = 8
RNG = np.random.default_rng(884)
N_PERM = 999
MEMBERS = ("ms", "impact", "osu", "uh")


def building_flags():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"])  # OSU pinned to v0 (paper basis)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(gp.METRIC_CRS).rename(
        columns={"ms_dmg": "dmg_ms", "sar_dmg": "dmg_impact", "osu_dmg": "dmg_osu",
                 "uh_dmg": "dmg_uh"})


def uh_aoi():
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    pts = g.geometry.representative_point()
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in pts}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def morans_i(cells, values):
    idx = {c: i for i, c in enumerate(cells)}
    nbr = [[idx[n] for n in h3.grid_disk(c, 1) if n != c and n in idx] for c in cells]
    keep = np.array([len(n) > 0 for n in nbr])
    if keep.sum() < 30:
        return np.nan, np.nan

    def stat(v):
        z = v - v.mean()
        lag = np.array([z[nb].mean() if nb else 0.0 for nb in nbr])
        return (z[keep] * lag[keep]).sum() / (z[keep] ** 2).sum()

    obs = stat(values)
    v = values.copy()
    perms = np.empty(N_PERM)
    for k in range(N_PERM):
        RNG.shuffle(v)
        perms[k] = stat(v)
    return obs, (np.sum(np.abs(perms) >= abs(obs)) + 1) / (N_PERM + 1)


def main():
    bld = building_flags()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ext = gp.cems_extent()
    latest = gp.to_metric(ext[ext.is_latest == True])  # noqa: E712
    areas = {n: s.geometry.make_valid().union_all() for n, s in latest.groupby("aoi_name")}
    aois = {
        "ms": gp.dissolve_union(gp.microsoft_aoi()),
        "impact": gp.dissolve_union(gp.impact_v2_aoi()),
        "osu": gp.dissolve_union(gp.osu_aoi()),
        "uh": uh_aoi(),
    }

    bld["cell"] = [h3.latlng_to_cell(p.y, p.x, RES)
                   for p in bld.to_crs(4326).geometry]
    cems_ll = cems.to_crs(4326)
    cems = cems.assign(cell=[h3.latlng_to_cell(p.y, p.x, RES) for p in cems_ll.geometry])

    rows = []
    for m in MEMBERS:
        in_aoi = bld.geometry.within(aois[m])
        cems_in_aoi = cems.geometry.within(aois[m])
        for area_name in list(areas) + ["ALL"]:
            if area_name == "ALL":
                bm = in_aoi & bld.geometry.within(
                    gpd.GeoSeries(list(areas.values()), crs=gp.METRIC_CRS).union_all())
                cm = cems_in_aoi & cems.geometry.within(
                    gpd.GeoSeries(list(areas.values()), crs=gp.METRIC_CRS).union_all())
            else:
                bm = in_aoi & bld.geometry.within(areas[area_name])
                cm = cems_in_aoi & cems.geometry.within(areas[area_name])
            sub = bld[bm]
            if len(sub) < 1000:
                continue
            d = (sub.groupby("cell")
                 .agg(base=("cell", "size"), pdmg=(f"dmg_{m}", "sum"))
                 .join(cems[cm].groupby("cell").size().rename("cems"))
                 .fillna(0))
            d = d[d.base >= 1]
            if len(d) < 30:
                continue
            X = sm.add_constant(np.log1p(d.cems.to_numpy()))
            fit = sm.GLM(d.pdmg.to_numpy(), X, family=sm.families.Poisson(),
                         offset=np.log(d.base.to_numpy())).fit()
            resid = np.asarray(fit.resid_pearson)
            i_, p_ = morans_i(d.index.tolist(), resid.copy())
            rows.append(dict(product=m.upper(), area=area_name, cells=len(d),
                             n_cems=int(d.cems.sum()), flag_pct=round(100 * d.pdmg.sum() / d.base.sum(), 1),
                             moran_I=round(i_, 3), p=round(p_, 4)))
            print(rows[-1], flush=True)

    out = pd.DataFrame(rows)
    csv = os.path.join(os.path.dirname(__file__), "..", "rq3b_per_area_moran.csv")
    out.to_csv(csv, index=False)
    print("\n", out.pivot(index="area", columns="product", values="moran_I").to_string())
    print("wrote", csv)


if __name__ == "__main__":
    main()
