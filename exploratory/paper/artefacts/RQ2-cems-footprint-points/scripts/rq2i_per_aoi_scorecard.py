"""RQ2i — per-CEMS-AOI scorecard: does performance collapse outside Caraballeda?

Motivation (user, 2026-07-27): 96% of CEMS latest {2,3} damage points sit in the
Caraballeda AOI (1,469 of 1,536), so every pooled scorecard number is effectively a
Caraballeda number. This script scores each product separately inside each CEMS AOI
(scorecard frame: gold centroids, OSU v0-pinned, r = 10 m), with crowd adjudication of
CEMS-unmatched flags per AOI — crucial outside Caraballeda, where CEMS is so thin that
low precision cannot distinguish product failure from reference incompleteness
(standing flag #1).

Per product x AOI: n_cems, n_flags, flag_share (of buildings in the region), P (CEMS
floor), R, crowd coverage of the CEMS-unmatched flags, share crowd-judged damaged, and
crowd-adjusted precision. Recall is suppressed (NaN) where n_cems < 20.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2i_per_aoi_scorecard.py
"""
from __future__ import annotations
import gzip, io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
R = 10
MIN_CEMS_FOR_RECALL = 20
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


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


def mapswipe_tasks():
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE")
    frames = []
    for b in cc.list_blobs(name_starts_with=pref):
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            rows = [f["properties"] for f in feats if f["properties"].get("h3")]
            if rows:
                frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= 4].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")["majority"]


def main():
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    prod_aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
                 "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
                 "OSU": gp.dissolve_union(gp.osu_aoi()),
                 "UH": uh_aoi(),
                 "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                       "analysed_extent.parquet")),
                 "UNEP": None}  # no extent: coverage assumption, scored in every AOI
    tasks = mapswipe_tasks()

    def crowd_verdicts(sub4326):
        out = []
        for p in sub4326.geometry:
            v = np.nan
            for res in (11, 12):
                c = h3.latlng_to_cell(p.y, p.x, res)
                if c in tasks.index:
                    v = int(tasks.loc[c])
                    break
            out.append(v)
        return pd.Series(out, index=sub4326.index)

    rows = []
    # "ALL (as delivered)" first: pooled across every CEMS AOI — the operational frame
    # (a responder receives the whole product, not just its best zone).
    groups = [("ALL (as delivered)", ext)] + [(a, s) for a, s in ext.groupby("aoi_name")]
    for aoi, sub in groups:
        region = sub.geometry.make_valid().union_all()
        cpts = cems[cems.geometry.within(region)]
        print(f"\n== {aoi}: {len(cpts):,} CEMS pts "
              f"({len(cpts)/len(cems):.0%} of all) ==")
        for nm, col in MEMBERS.items():
            reg = region if prod_aois[nm] is None else region.intersection(prod_aois[nm])
            if reg.is_empty:
                continue
            inb = bld[bld.geometry.within(reg)]
            if len(inb) < 50:
                continue
            fl = inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1]
            ca = cpts[cpts.geometry.within(reg)]
            row = dict(aoi=aoi, product=nm, n_bld=len(inb), n_flags=len(fl),
                       flag_share=round(len(fl) / len(inb), 3), n_cems=len(ca))
            if len(fl) and len(ca):
                ct = cKDTree(np.c_[ca.geometry.x, ca.geometry.y])
                hit = ct.query(np.c_[fl.geometry.x, fl.geometry.y], k=1)[0] <= R
                row["P_cems"] = round(float(hit.mean()), 3)
                ft = cKDTree(np.c_[fl.geometry.x, fl.geometry.y])
                rd = ft.query(np.c_[ca.geometry.x, ca.geometry.y], k=1)[0] <= R
                row["R_cems"] = round(float(rd.mean()), 3) if len(ca) >= MIN_CEMS_FOR_RECALL else np.nan
            elif len(fl):
                row["P_cems"] = 0.0 if len(ca) == 0 else np.nan
                row["R_cems"] = np.nan
            # crowd adjudication of the CEMS-unmatched flags
            if len(fl):
                if len(ca):
                    fpm = fl[~hit]
                else:
                    fpm = fl
                cv = crowd_verdicts(fpm.to_crs(4326)) if len(fpm) else pd.Series(dtype=float)
                cov = float(cv.notna().mean()) if len(cv) else np.nan
                conf = float((cv == 1).mean()) if cv.notna().any() else np.nan
                row["crowd_cov_of_fps"] = round(cov, 2) if cov == cov else np.nan
                row["fp_crowd_damaged"] = round(conf, 2) if conf == conf else np.nan
                if conf == conf and len(fl):
                    tp = int(hit.sum()) if len(ca) else 0
                    row["P_crowd_adj"] = round((tp + len(fpm) * conf) / len(fl), 3)
            rows.append(row)
            print(row)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2i_per_aoi_scorecard.csv"), index=False)
    print("\nwrote rq2i_per_aoi_scorecard.csv")

    # ---- heatmap: precision + recall per product x AOI --------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    aois = (out[out.aoi != "ALL (as delivered)"]
            .groupby("aoi").n_cems.max().sort_values(ascending=False)).index.tolist()
    aois = ["ALL (as delivered)"] + aois
    prods = list(MEMBERS)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.5))
    for ax, colname, title in ((axes[0], "P_cems", "precision (CEMS floor, r = 10 m)"),
                               (axes[1], "R_cems", "recall (CEMS, r = 10 m)")):
        M = np.full((len(prods), len(aois)), np.nan)
        for i, p in enumerate(prods):
            for j, a in enumerate(aois):
                r = out[(out["product"] == p) & (out.aoi == a)]
                if len(r) and r[colname].notna().any():
                    M[i, j] = float(r[colname].iloc[0])
        im = ax.imshow(M, cmap="YlOrRd", vmin=0, vmax=np.nanmax(M), aspect="auto")
        for i in range(len(prods)):
            for j in range(len(aois)):
                r = out[(out["product"] == prods[i]) & (out.aoi == aois[j])]
                if not len(r):
                    ax.text(j, i, "no\noverlap", ha="center", va="center", fontsize=8,
                            color="#777")
                elif np.isnan(M[i, j]):
                    ax.text(j, i, "ref too\nthin", ha="center", va="center", fontsize=8,
                            color="#777")
                else:
                    dark = M[i, j] > 0.6 * np.nanmax(M)
                    ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center", fontsize=10,
                            color="white" if dark else "#1b1f24", weight="bold")
        ax.set_xticks(range(len(aois)),
                      [f"{a}\n(n={int(out[out.aoi == a].n_cems.max())})" for a in aois],
                      fontsize=10)
        ax.set_yticks(range(len(prods)), prods, fontsize=11)
        ax.set_title(title, fontsize=12)
    fig.suptitle("The scorecard is not one number per product: per-CEMS-AOI performance\n"
                 "(96% of reference damage points sit in Caraballeda; n = CEMS {2,3} "
                 "points per AOI)", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq2i_per_aoi_scorecard.png"), dpi=150)
    print("wrote figs/rq2i_per_aoi_scorecard.png")


if __name__ == "__main__":
    main()
