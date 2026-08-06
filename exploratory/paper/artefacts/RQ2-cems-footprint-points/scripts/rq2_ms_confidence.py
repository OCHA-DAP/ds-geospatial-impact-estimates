"""RQ2d — Microsoft's own confidence axis: the damage_pct_10m operating curve.

MS silver carries continuous per-building fields we binarise everywhere: damage_pct_10m
(0-1 damage fraction), num_observations (1-3 scenes), uncertainty (sparse). This pass:
  1. Sweeps damage_pct_10m as a threshold -> MS's own P-R curve (dual-anchor r=10 m vs CEMS
     {2,3}, native footprints, region = CEMS latest extent ∩ MS AOI) with the SHIPPED binary
     flag marked on it — was Microsoft's operating point well chosen?
  2. Stratifies the shipped flag by num_observations (1 vs 2+ scenes): self-corroboration.
  3. Bonus: recall of the shipped flag against the NEW ChatMap field-validated damage points
     (415 pts, bronze/source=mapswipe/hdx) within the MS AOI.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2_ms_confidence.py
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
R = 10


def ms_all():
    """All non-superseded MS footprints (not just damaged) with the continuous fields."""
    g = gp._read_pq("silver", "source=microsoft", "adm0=VE", "footprints.parquet")
    return g[~g.superseded.astype(bool)].copy()


def chatmap():
    import ocha_stratus as stratus
    b = stratus.load_blob_data(
        gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", "hdx",
                       "chatmap_field_validated_damage_points.geojson"),
        stage="dev", container_name=gp.S.container)
    return gpd.GeoDataFrame.from_features(json.loads(b)["features"], crs=4326).to_crs(gp.METRIC_CRS)


def pr(flagged, truth_pts):
    nr, dr = gp.match_rate(truth_pts, flagged, R)
    np_, dp = gp.match_rate(flagged, truth_pts, R)
    rec = nr / dr if dr else np.nan
    prec = np_ / dp if dp else np.nan
    f1 = 2 * prec * rec / (prec + rec) if (prec or 0) + (rec or 0) > 0 else 0.0
    return prec, rec, f1


def main():
    ms = gp.to_metric(ms_all())
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    ext = gp.cems_extent()
    region = (gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
              .intersection(gp.dissolve_union(gp.microsoft_aoi())))
    in_reg = ms.geometry.representative_point().within(region)
    msr = ms[in_reg]
    cpts = cems[cems.geometry.within(region)]
    print(f"region: {len(msr):,} MS footprints, {int(msr.damaged.sum()):,} shipped-damaged, "
          f"{len(cpts):,} CEMS pts")

    # 1. damage_pct sweep + shipped point
    rows = []
    for t in np.round(np.arange(0.02, 0.96, 0.03), 2):
        f = msr[msr.damage_pct_10m >= t]
        prec, rec, f1 = pr(f, cpts)
        rows.append(dict(thresh=t, n_flag=len(f), precision=round(prec, 3),
                         recall=round(rec, 3), f1=round(f1, 3)))
    curve = pd.DataFrame(rows)
    sp, sr, sf = pr(msr[msr.damaged == 1], cpts)
    print(f"shipped binary flag: P={sp:.3f} R={sr:.3f} F1={sf:.3f} "
          f"(curve max F1={curve.f1.max():.3f} at t={curve.loc[curve.f1.idxmax(), 'thresh']})")
    curve.to_csv(os.path.join(HERE, "..", "rq2_ms_confidence_curve.csv"), index=False)

    # 2. num_observations strata (shipped flag)
    print("\nnum_observations strata (shipped damaged flag):")
    for nm, sub in (("1 scene", msr[(msr.damaged == 1) & (msr.num_observations == 1)]),
                    ("2+ scenes", msr[(msr.damaged == 1) & (msr.num_observations >= 2)])):
        prec, rec, f1 = pr(sub, cpts)
        print(f"  {nm:9s}: n={len(sub):5,}  P={prec:.3f}  (recall-if-alone R={rec:.3f})")

    # 3. ChatMap field points: does shipped MS find field-confirmed damage?
    field = chatmap()
    fin = field[field.geometry.within(gp.dissolve_union(gp.microsoft_aoi()))]
    for r_ in (10, 20):
        n, d = gp.match_rate(fin, ms[ms.damaged == 1], r_)
        print(f"\nChatMap field points in MS AOI: {d} | with shipped MS flag within {r_} m: "
              f"{n} ({n/d:.0%})" if d else "no field points in MS AOI")

    fig, ax = plt.subplots(figsize=(7, 5.6))
    ax.plot(curve.recall, curve.precision, "-o", ms=3, c="black", label="MS damage_pct_10m sweep")
    for t in (0.05, 0.2, 0.5, 0.8):
        r_ = curve.iloc[(curve.thresh - t).abs().idxmin()]
        ax.annotate(f"≥{r_.thresh}", (r_.recall, r_.precision),
                    textcoords="offset points", xytext=(5, 4), fontsize=8)
    ax.scatter([sr], [sp], c="tab:red", s=90, zorder=5, marker="*",
               label=f"shipped binary flag (P={sp:.2f}, R={sr:.2f})")
    try:
        rq5 = pd.read_csv(os.path.join(HERE, "..", "..", "RQ5-ensemble", "rq5_summary.csv"))
        k4 = rq5[rq5.rule.isin(["3-of-4", "4-of-4"])]
        ax.scatter(k4.recall_r10, k4.precision_r10, c="tab:blue", marker="D",
                   label="ensemble 3-of-4 / 4-of-4 (RQ5, centroid basis)")
        for _, rr in k4.iterrows():
            ax.annotate(rr.rule, (rr.recall_r10, rr.precision_r10),
                        textcoords="offset points", xytext=(5, 4), fontsize=8)
    except FileNotFoundError:
        pass
    ax.set_xlabel("recall (CEMS {2,3}, r=10 m)"); ax.set_ylabel("precision")
    ax.set_title("RQ2d — Microsoft's own operating curve (native footprints, MS∩CEMS region)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq2_ms_confidence_curve.png"), dpi=130)
    print("wrote figs/rq2_ms_confidence_curve.png")


if __name__ == "__main__":
    main()
