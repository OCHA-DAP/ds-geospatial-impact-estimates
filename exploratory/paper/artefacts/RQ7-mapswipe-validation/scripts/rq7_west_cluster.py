"""RQ7 (value demo, pre-ingestion) — does the MapSwipe crowd adjudicate the Microsoft
west-Caraballeda over-detection cluster?

RQ3b found MS's error is one hard spatial clump (west strip, I=0.60) that covariates can't
explain, with two rival attributions: (a) genuine MS false positives, (b) CEMS builtUpP
under-enumeration peaking there. The HOT MapSwipe campaign (raw exports, scratchpad — NOT yet
in the lake) has 428 volunteers voting 0=No damage / 1=Damaged / 2=Not sure on ~3,900
MS-seeded H3 res-11 hexes across the same strip (projects 3179 Catia La Mar/west +
3178 Caraballeda/east).

Test: aggregate crowd verdicts to H3 res-8 (parents of the res-11 tasks), join to the RQ3b
exposure-GLM Pearson residuals (MS, res 8), and ask whether crowd REJECTION of MS-flagged
hexes rises with the residual. If (a): high-residual cells -> high majority-0 share. If (b):
high-residual cells -> crowd confirms damage CEMS missed (high 1-share).

Run: uv run --group etl --with statsmodels --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ7-mapswipe-validation/scripts/rq7_west_cluster.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import statsmodels.api as sm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, mannwhitneyu

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

MS_DIR = ("/private/tmp/claude-501/-Users-zackarno-Documents-CHD-repos-ds-geospatial-impact-estimates"
          "/6a2963d5-ef5a-4570-85b7-87c84e12fb21/scratchpad/mapswipe")
FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)


def ms_residuals():
    """RQ3b exposure-spec Pearson residuals for Microsoft, per res-8 cell (same as explainer)."""
    import ocha_stratus as stratus
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    ms = gp.to_metric(gp.microsoft())
    region = ext_latest.intersection(gp.dissolve_union(gp.microsoft_aoi()))
    b = stratus.load_blob_data(
        gp.S.blob_path("gold", "model=common", "adm0=VE", "building_flags.parquet"),
        stage="dev", container_name=gp.S.container)
    df = pd.read_parquet(io.BytesIO(b), columns=["lon", "lat"])
    base = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                            crs=4326).to_crs(gp.METRIC_CRS)

    def counts(g, nm):
        sub = g[g.geometry.representative_point().within(region)]
        ll = sub.to_crs(4326).geometry.representative_point()
        return pd.Series([h3.latlng_to_cell(p.y, p.x, 8) for p in ll]).value_counts().rename(nm)

    d = pd.concat([counts(base, "base"), counts(cems, "cems"), counts(ms, "pdmg")],
                  axis=1).fillna(0)
    d = d[d.base >= 1]
    X = sm.add_constant(np.log1p(d.cems.to_numpy()))
    fit = sm.GLM(d.pdmg.to_numpy(), X, family=sm.families.Poisson(),
                 offset=np.log(d.base.to_numpy())).fit()
    d["resid"] = np.asarray(fit.resid_pearson)
    return d


def mapswipe_hexes():
    """MS-flagged validation tasks from 3179 (west) + 3178 (east), with crowd vote shares.
    Reads from BRONZE (not scratchpad — that gets wiped)."""
    import gzip, json
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    frames = []
    for pid in (3179, 3178):
        pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", f"project={pid}")
        for b in cc.list_blobs(name_starts_with=pref):
            if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
                feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
                gi = gpd.GeoDataFrame.from_features(feats, crs=4326)
                gi["pid"] = pid
                frames.append(gi)
    g = pd.concat(frames, ignore_index=True)
    g = g[g["sources"].str.contains("microsoft", case=False, na=False)].copy()
    g["parent8"] = [h3.cell_to_parent(c, 8) for c in g["h3"]]
    g["majority"] = g[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return g


def main():
    d = ms_residuals()
    ms_hex = mapswipe_hexes()
    print(f"MapSwipe MS-flagged tasks: {len(ms_hex):,} "
          f"(west/3179: {(ms_hex.pid == 3179).sum():,}, east/3178: {(ms_hex.pid == 3178).sum():,})")

    per8 = (ms_hex.groupby("parent8")
            .agg(n_tasks=("task_id", "size"),
                 conf_share=("1_share", "mean"),     # crowd 'damaged'
                 rej_share=("0_share", "mean"),      # crowd 'no damage'
                 unsure_share=("2_share", "mean"),
                 maj0=("majority", lambda s: (s == 0).mean()),
                 maj1=("majority", lambda s: (s == 1).mean()),
                 votes=("total_count", "sum")))
    j = per8.join(d, how="inner")
    print(f"res-8 cells with both RQ3b residual and crowd data: {len(j)} "
          f"(covering {int(j.n_tasks.sum()):,} tasks, {int(j.votes.sum()):,} votes)")

    rho_rej, p_rej = spearmanr(j.resid, j.rej_share)
    rho_conf, p_conf = spearmanr(j.resid, j.conf_share)
    print(f"\nSpearman residual vs crowd REJECTION share: rho={rho_rej:+.3f} (p={p_rej:.2g})")
    print(f"Spearman residual vs crowd CONFIRMATION share: rho={rho_conf:+.3f} (p={p_conf:.2g})")

    top = j[j.resid >= j.resid.quantile(0.8)]
    rest = j[j.resid < j.resid.quantile(0.8)]
    u, pu = mannwhitneyu(top.rej_share, rest.rej_share, alternative="greater")
    print(f"\nTop-quintile residual cells (n={len(top)}, the 'cluster'): "
          f"rejection {top.rej_share.mean():.2f}, confirmation {top.conf_share.mean():.2f}")
    print(f"Rest (n={len(rest)}): rejection {rest.rej_share.mean():.2f}, "
          f"confirmation {rest.conf_share.mean():.2f}")
    print(f"Mann-Whitney (top rejection > rest): p={pu:.2g}")

    # west (3179) vs east (3178) headline
    for pid, nm in ((3179, "WEST Catia La Mar"), (3178, "EAST Caraballeda")):
        s = ms_hex[ms_hex.pid == pid]
        print(f"{nm}: maj-No {(s.majority == 0).mean():.0%}, maj-Yes {(s.majority == 1).mean():.0%}, "
              f"maj-Unsure {(s.majority == 2).mean():.0%}  (n={len(s):,})")

    j.reset_index().rename(columns={"index": "h3_res8"}).to_csv(
        os.path.join(os.path.dirname(__file__), "..", "rq7_west_cluster_join.csv"), index=False)

    # FIGURE MOVED (2026-08-05) to scripts/rq7_west_cluster_fig.py, which reads the CSV
    # written just above. This script no longer draws it.
    #
    # It used to draw two maps titled "the over-flagged western cluster is EXACTLY where
    # volunteers saw no damage", having dropped the scatter panel that showed the cell-scale
    # relationship as "confusing". But that relationship is the null printed above
    # (rho = +0.09, p = 0.39), so the two remaining maps asserted a cell-by-cell coincidence
    # the statistics rule out. The adjudication is real at STRIP scale (71% west vs 49/48
    # east) and the rebuilt figure says so, with the scatter restored.
    print("figure: run scripts/rq7_west_cluster_fig.py (reads rq7_west_cluster_join.csv)")


if __name__ == "__main__":
    main()
