"""RQ3e — can REFERENCE-FREE spatial statistics predict CEMS-measured performance?

User question: areas where the spatial stats look pathological — do they also score worse
against CEMS? If a statistic computable WITHOUT any reference predicts CEMS-measured
precision across (product × area) pairs, the reliability assessment generalises to areas
CEMS never covered.

Per (product × CEMS area), three reference-free predictors:
  flag_pct    share of buildings flagged (product's own aggressiveness)
  moran_flags Moran's I of the product's raw flag-RATE field per res-8 cell (its own
              spatial pattern; NO CEMS involved — unlike RQ3b/3d residual stats)
  peer_agree  share of the product's flags corroborated by >=1 OTHER product on the same
              building (uses peers as pseudo-reference; still no CEMS)
Outcome: CEMS-measured per-area precision and lift (from RQ2c rq2_density_null.csv).
Test: Spearman correlation across pairs (n is small — exploratory, stated).

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3e_reference_free.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.stats import spearmanr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
RES = 8
FLAGS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
         "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
NAMEMAP = {"MS": "MS", "IMPACT": "IMPACT", "OSU": "OSU", "UH": "UH"}  # rq2c uses these


def moran_of(cells, values):
    idx = {c: i for i, c in enumerate(cells)}
    nbr = [[idx[n] for n in h3.grid_disk(c, 1) if n != c and n in idx] for c in cells]
    keep = np.array([len(n) > 0 for n in nbr])
    if keep.sum() < 20:
        return np.nan
    z = values - values.mean()
    lag = np.array([z[nb].mean() if nb else 0.0 for nb in nbr])
    denom = (z[keep] ** 2).sum()
    return float((z[keep] * lag[keep]).sum() / denom) if denom > 0 else np.nan


def main():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    votes = df[list(FLAGS.values())].sum(axis=1)
    ll = bld.to_crs(4326)
    bld["cell"] = [h3.latlng_to_cell(p.y, p.x, RES) for p in ll.geometry]

    ext = gp.cems_extent()
    latest = gp.to_metric(ext[ext.is_latest == True])  # noqa: E712
    areas = {n: s.geometry.make_valid().union_all() for n, s in latest.groupby("aoi_name")}

    rows = []
    for area_name, geom in areas.items():
        am = bld.geometry.within(geom)
        for nm, col in FLAGS.items():
            sub = bld[am]
            if len(sub) < 1000:
                continue
            flagged = sub[df.loc[sub.index, col] == 1]
            if len(flagged) < 30:
                continue
            d = sub.groupby("cell").agg(base=("cell", "size"))
            d["pdmg"] = flagged.groupby("cell").size().reindex(d.index).fillna(0)
            rate = (d.pdmg / d.base).to_numpy()
            peer = ((votes.loc[flagged.index] - 1) >= 1).mean()
            rows.append(dict(product=nm, area=area_name,
                             flag_pct=round(100 * len(flagged) / len(sub), 1),
                             moran_flags=round(moran_of(d.index.tolist(), rate), 3),
                             peer_agree=round(peer, 2)))
    pred = pd.DataFrame(rows)

    perf = pd.read_csv(os.path.join(HERE, "..", "..", "RQ2-cems-footprint-points",
                                    "rq2_density_null.csv"))
    m = pred.merge(perf[["product", "area", "precision", "lift", "enrichment"]],
                   on=["product", "area"], how="inner").dropna(subset=["precision"])
    print(m.to_string(index=False))
    print(f"\nn = {len(m)} (product × area) pairs with CEMS-measured precision")
    for p in ("flag_pct", "moran_flags", "peer_agree"):
        for o in ("precision", "lift"):
            rho, pv = spearmanr(m[p], m[o])
            print(f"  {p:12s} vs {o:9s}: rho={rho:+.2f} (p={pv:.3f})")
    m.to_csv(os.path.join(HERE, "..", "rq3e_reference_free.csv"), index=False)
    print("wrote rq3e_reference_free.csv")

    # the generalisation gesture: predictors for areas with NO CEMS-measured performance
    nocems = pred[~pred.set_index(["product", "area"]).index.isin(
        m.set_index(["product", "area"]).index)]
    if len(nocems):
        print("\nreference-free predictors where CEMS metrics are unavailable/weak:")
        print(nocems.to_string(index=False))


if __name__ == "__main__":
    main()
