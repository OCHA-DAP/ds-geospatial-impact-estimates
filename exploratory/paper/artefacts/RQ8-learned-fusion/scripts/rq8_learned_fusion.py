"""RQ8 — learned fusion: logistic + random forest over the six products vs the k-of-6 dial.

See ../DESIGN.md. Spatial block CV (GroupKFold on H3 res-7), label = CEMS {2,3} within 20 m,
crowd-gap buildings weight-0 in training (sensitivity: weight 1). All reported numbers are
pooled out-of-fold predictions.

Run: uv run --group etl --with scikit-learn --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8_learned_fusion.py
"""
from __future__ import annotations
import gzip, io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import average_precision_score, precision_recall_curve

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)
LABEL_R = 20
FLAGS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
         "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
CLASSES = ["uh_class", "sar_class", "osu_class", "list_class"]


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


def crowd_damaged_cells():
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE")
    cells = set()
    for b in cc.list_blobs(name_starts_with=pref):
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            for f in feats:
                p = f["properties"]
                if p.get("h3") and p.get("total_count", 0) >= 4:
                    shares = (p.get("0_share", 0), p.get("1_share", 0), p.get("2_share", 0))
                    if int(np.argmax(shares)) == 1:
                        cells.add(p["h3"])
    return cells


def main():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values(), *CLASSES])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    d = bld[bld.geometry.within(region)].copy().reset_index(drop=True)

    # ---- label: CEMS {2,3} within LABEL_R ----
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    dist, _ = ct.query(np.c_[d.geometry.x, d.geometry.y], k=1)
    d["y"] = (dist <= LABEL_R).astype(int)

    # ---- MS continuous features (nearest MS footprint centroid <= 20 m) ----
    ms = gp.to_metric(gp.microsoft())  # damaged, non-superseded
    ms_all = gp._read_pq("silver", "source=microsoft", "adm0=VE", "footprints.parquet")
    ms_all = gp.to_metric(ms_all[~ms_all.superseded.astype(bool)])
    mc = ms_all.geometry.representative_point()
    mt = cKDTree(np.c_[mc.x, mc.y])
    md, mi = mt.query(np.c_[d.geometry.x, d.geometry.y], k=1)
    near = md <= 20
    d["ms_pct"] = np.where(near, ms_all.damage_pct_10m.to_numpy()[mi], 0.0)
    d["ms_nobs"] = np.where(near, ms_all.num_observations.to_numpy()[mi], 0)

    # ---- context features ----
    ll = d.to_crs(4326)
    d["cell7"] = [h3.latlng_to_cell(p.y, p.x, 7) for p in ll.geometry]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    d["density9"] = cell9.map(cell9.value_counts())
    adm0 = gp.codab(0)
    coast = gp.to_metric(adm0).geometry.make_valid().union_all().boundary
    d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    # MMI: nearest contour, max over events
    frames = []
    for ev in ("us6000t7zp", "us6000t7zc"):
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json"),
            stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)
        frames.append(g[["value", "geometry"]])
    mmi = np.full(len(d), np.nan)
    for g in frames:
        j = gpd.sjoin_nearest(d[["geometry"]], g, how="left")
        j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    d["mmi"] = np.nan_to_num(mmi, nan=np.nanmedian(mmi))

    for c in CLASSES:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    # ---- crowd-gap mask: crowd says damaged, CEMS says nothing -> weight 0 ----
    cd = crowd_damaged_cells()
    cell11 = pd.Series([h3.latlng_to_cell(p.y, p.x, 11) for p in ll.geometry])
    crowd_gap = cell11.isin(cd).to_numpy() & (d.y.to_numpy() == 0)
    w = np.where(crowd_gap, 0.0, 1.0)
    print(f"region buildings {len(d):,} | positives {d.y.sum():,} ({d.y.mean():.1%}) | "
          f"crowd-gap weight-0 negatives {int(crowd_gap.sum()):,}")

    FEATS = ([*FLAGS.values()] + CLASSES + ["ms_pct", "ms_nobs", "density9", "dist_coast", "mmi"])
    X = d[FEATS].astype(float).fillna(0.0).to_numpy()
    y = d.y.to_numpy()
    groups = d.cell7.to_numpy()
    print(f"features: {FEATS} | spatial blocks (res-7): {d.cell7.nunique()}")

    models = {
        "logit": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "rf": RandomForestClassifier(n_estimators=400, min_samples_leaf=20,
                                     class_weight="balanced_subsample", n_jobs=-1,
                                     random_state=884),
    }
    gkf = GroupKFold(n_splits=5)
    oof = {m: np.zeros(len(d)) for m in models}
    for tr, te in gkf.split(X, y, groups):
        for name, mdl in models.items():
            # z-score continuous features on train only (logit needs it; harmless for RF)
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            mdl.fit((X[tr] - mu) / sd, y[tr], sample_weight=w[tr])
            oof[name][te] = mdl.predict_proba((X[te] - mu) / sd)[:, 1]

    # ---- ablation: is the skill products or geography? ----
    CONTEXT = ["density9", "dist_coast", "mmi"]
    PRODUCTS = [f for f in FEATS if f not in CONTEXT]
    abl_scores = {}
    for abl_name, cols in (("context-only", CONTEXT), ("products-only", PRODUCTS)):
        idx = [FEATS.index(c) for c in cols]
        s = np.zeros(len(d))
        for tr, te in gkf.split(X, y, groups):
            mu, sd = X[tr][:, idx].mean(0), X[tr][:, idx].std(0) + 1e-9
            m = RandomForestClassifier(n_estimators=400, min_samples_leaf=20,
                                       class_weight="balanced_subsample", n_jobs=-1,
                                       random_state=884)
            m.fit((X[tr][:, idx] - mu) / sd, y[tr], sample_weight=w[tr])
            s[te] = m.predict_proba((X[te][:, idx] - mu) / sd)[:, 1]
        abl_scores[abl_name] = s

    votes = d[list(FLAGS.values())].sum(axis=1).to_numpy()
    rows = []
    for name, score in [("logit", oof["logit"]), ("rf", oof["rf"]),
                        ("rf context-only (NO products)", abl_scores["context-only"]),
                        ("rf products-only (NO context)", abl_scores["products-only"]),
                        ("votes(k-of-6)", votes)]:
        ap = average_precision_score(y, score)
        rows.append(dict(model=name, avg_precision=round(ap, 3)))
        print(rows[-1])
    single_ap = {}
    for nm, col in FLAGS.items():
        s = d[col].to_numpy(dtype="float64", na_value=0.0)
        single_ap[nm] = average_precision_score(y, s)
        rows.append(dict(model=f"single: {nm}", avg_precision=round(single_ap[nm], 3)))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq8_summary.csv"), index=False)

    # final-fit importances / weights (full data, for interpretation only)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    rf = models["rf"].fit((X - mu) / sd, y, sample_weight=w)
    lg = models["logit"].fit((X - mu) / sd, y, sample_weight=w)
    imp = pd.DataFrame({"feature": FEATS,
                        "rf_importance": np.round(rf.feature_importances_, 3),
                        "logit_coef": np.round(lg.coef_[0], 2)}
                       ).sort_values("rf_importance", ascending=False)
    imp.to_csv(os.path.join(HERE, "..", "rq8_importances.csv"), index=False)
    print(imp.to_string(index=False))

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.8))
    for name, score, c in (("random forest", oof["rf"], "tab:red"),
                           ("logistic", oof["logit"], "tab:blue"),
                           ("k-of-6 votes", votes, "black")):
        p, r, _ = precision_recall_curve(y, score)
        ap = average_precision_score(y, score)
        ax[0].plot(r, p, c=c, lw=1.6, label=f"{name} (AP={ap:.2f})")
    ax[0].set_xlabel("recall (CEMS {2,3} within 20 m)"); ax[0].set_ylabel("precision")
    ax[0].set_title("out-of-fold PR — spatial block CV (res-7 groups)", fontsize=10)
    ax[0].legend(fontsize=8)
    top = imp.head(10)[::-1]
    ax[1].barh(top.feature, top.rf_importance, color="tab:red", alpha=.8)
    ax[1].set_title("random-forest feature importance (top 10)", fontsize=10)
    fig.suptitle("RQ8 — learned fusion vs the flat voting dial")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq8_learned_fusion.png"), dpi=130)
    print("wrote figs/rq8_learned_fusion.png")

    # ---- figure: the day-zero baseline vs every single product ------------------
    # Top: map of what the no-satellite model predicts, with real CEMS damage on top.
    # Bottom-left: AP bars incl. a BINARY day-zero rule (thresholded at the median
    # product flag count) so binary classifiers compare like-for-like. Bottom-right:
    # PR plane — the continuous scores are curves (every threshold = a different
    # binary rule), shipped products are single points (provider already thresholded).
    from matplotlib.patches import Polygon as MplPolygon
    geo_ap = average_precision_score(y, abl_scores["context-only"])
    fus_ap = average_precision_score(y, oof["logit"])
    vote_ap = average_precision_score(y, votes)

    fig = plt.figure(figsize=(12.5, 18))
    gs = fig.add_gridspec(3, 1, height_ratios=[0.85, 0.9, 1.5], hspace=0.25)
    axm = fig.add_subplot(gs[0])
    axbar = fig.add_subplot(gs[1])
    axb = fig.add_subplot(gs[2])
    ll4 = d.to_crs(4326)
    land = gp.codab(0).geometry.make_valid().union_all()
    axm.set_facecolor("#e7f0f6")
    for g in getattr(land, "geoms", [land]):
        axm.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                 facecolor="#f1f0ea", edgecolor="#b9b7ae", lw=1.0, zorder=0))
    risk = abl_scores["context-only"]
    order = np.argsort(risk)  # draw high-risk buildings on top
    sc = axm.scatter(ll4.geometry.x.to_numpy()[order], ll4.geometry.y.to_numpy()[order],
                     c=risk[order], cmap="YlOrRd", s=3, zorder=2)
    cll = cems.to_crs(4326)
    axm.scatter(cll.geometry.x, cll.geometry.y, s=6, c="k", marker=".",
                zorder=3, label="CEMS damage point")
    pad = 0.008
    axm.set_xlim(ll4.geometry.x.min() - pad, ll4.geometry.x.max() + pad)
    axm.set_ylim(ll4.geometry.y.min() - pad, ll4.geometry.y.max() + pad)
    axm.set_aspect("equal")
    axm.set_xticks([]); axm.set_yticks([])
    plt.colorbar(sc, ax=axm, shrink=0.75, pad=0.01, label="predicted damage risk")
    axm.legend(loc="lower left", fontsize=11)
    axm.set_title("What the day-zero variables alone predict — no satellite input\n"
                  "(coast distance + building density + ShakeMap intensity)", fontsize=13)

    # bottom-left: AP bars, singles vs a binary day-zero rule vs combinations
    med_flags = int(np.median([int((d[c].to_numpy(dtype="float64", na_value=0.0) == 1).sum())
                               for c in FLAGS.values()]))
    thr = np.partition(risk, -med_flags)[-med_flags]
    geo_bin = (risk >= thr).astype(float)
    geo_bin_ap = average_precision_score(y, geo_bin)
    single_aps = {nm: average_precision_score(y, d[c].to_numpy(dtype="float64", na_value=0.0))
                  for nm, c in FLAGS.items()}
    names = sorted(single_aps, key=single_aps.get)
    labels = ["day-zero binary rule", *names,
              "flat 6-member voting", "weighted fusion"]
    vals = [geo_bin_ap, *(single_aps[n] for n in names), vote_ap, fus_ap]
    colors = ["#e34948"] + ["#9aa5b1"] * len(names) + ["#2a78d6", "#1b4f8a"]
    ypos = np.arange(len(labels), dtype=float)
    ypos[-2:] += 0.5
    axbar.barh(ypos, vals, color=colors, zorder=2)
    axbar.set_yticks(ypos, labels, fontsize=12)
    axbar.tick_params(axis="x", labelsize=11)
    axbar.axvline(geo_ap, color="#e34948", lw=1.8, ls="--", zorder=3)
    axbar.text(geo_ap + 0.004, ypos[0] + 0.35, f"day-zero score ({geo_ap:.2f})",
               color="#e34948", fontsize=11, va="bottom")
    axbar.set_xlabel("average precision (spatial-block CV, CEMS {2,3} target)", fontsize=12)
    axbar.set_title("Six products vs the no-satellite rule", fontsize=13)
    print(f"binary day-zero rule @ {med_flags:,} flags: AP={geo_bin_ap:.3f} | "
          f"P={((geo_bin == 1) & (y == 1)).sum() / geo_bin.sum():.3f} "
          f"R={((geo_bin == 1) & (y == 1)).sum() / y.sum():.3f}")

    # bottom-right: every threshold of the day-zero score IS a binary predictor, so its
    # PR curve is the family of day-zero rules; each product is one (recall, precision)
    # point to compare against that family, in the same frame (CEMS {2,3} within 20 m).
    p_geo, r_geo, _ = precision_recall_curve(y, risk)
    axb.plot(r_geo, p_geo, c="#e34948", lw=2.5, ls="--", zorder=3,
             label=f"day-zero rule family (AP={geo_ap:.2f})")
    p_f, r_f, _ = precision_recall_curve(y, oof["logit"])
    axb.plot(r_f, p_f, c="#1b4f8a", lw=2.2, zorder=2,
             label=f"weighted 6-product fusion (AP={fus_ap:.2f})")
    gb_tp = int(((geo_bin == 1) & (y == 1)).sum())
    axb.scatter(gb_tp / max(int(y.sum()), 1), gb_tp / max(int(geo_bin.sum()), 1),
                c="#e34948", s=110, marker="D", zorder=5,
                label=f"day-zero rule, binarized ({med_flags:,} flags)")
    # flat voting is a discrete score: its whole PR "curve" is six operating points
    first = True
    for k in range(1, 7):
        sel = votes >= k
        ktp = int((sel & (y == 1)).sum())
        kp, kr = ktp / max(int(sel.sum()), 1), ktp / max(int(y.sum()), 1)
        axb.scatter(kr, kp, c="#2a78d6", s=170, marker="s", zorder=5,
                    label="k-of-6 voting rules (k in the square)" if first else None)
        axb.annotate(str(k), (kr, kp), ha="center", va="center", fontsize=10,
                     color="white", zorder=6)
        first = False
    print("\nday-zero binary rule at each product's flag count (same frame):")
    offsets = {"UH": (-20, 6), "UNEP": (5, -11)}
    for nm, col in FLAGS.items():
        s = d[col].to_numpy(dtype="float64", na_value=0.0)
        nflag = int((s == 1).sum())
        tp = int(((s == 1) & (y == 1)).sum())
        prec, rec = tp / max(nflag, 1), tp / max(int(y.sum()), 1)
        axb.scatter(rec, prec, c="#4a5560", s=80, zorder=4)
        axb.annotate(nm, (rec, prec), textcoords="offset points",
                     xytext=offsets.get(nm, (7, 5)), fontsize=11, color="#4a5560")
        thr = np.partition(risk, -nflag)[-nflag]
        gsel = risk >= thr
        gtp = int((gsel & (y == 1)).sum())
        print(f"  {nm:6s}: {nflag:6,} flags -> P={prec:.3f} R={rec:.3f} | "
              f"day-zero rule at same count: P={gtp/max(gsel.sum(),1):.3f} "
              f"R={gtp/max(int(y.sum()),1):.3f}")
    axb.set_xlim(0, 1)
    axb.set_ylim(0, max(0.45, p_f.max() * 1.05))
    axb.set_xlabel("recall (CEMS {2,3} within 20 m)", fontsize=12)
    axb.set_ylabel("precision", fontsize=12)
    axb.tick_params(labelsize=11)
    axb.legend(fontsize=11, loc="upper right")
    axb.set_title("Single products sit just above the day-zero curve;\n"
                  "combining them is what changes the picture", fontsize=13)
    fig.tight_layout()
    fig.subplots_adjust(left=0.18)  # room for the bar-chart labels
    fig.savefig(os.path.join(FIGS, "rq8_geography_baseline.png"), dpi=150)
    print("wrote figs/rq8_geography_baseline.png")


if __name__ == "__main__":
    main()
