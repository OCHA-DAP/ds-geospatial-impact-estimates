"""RQ9 — block-bootstrap confidence intervals for the paper's headline numbers
(OPEN-ITEMS item 2, spec of 2026-08-10).

Design: spatial block bootstrap. Match indicators are computed ONCE on the full
frozen data (mirroring rq5b / rq2i / rq8 exactly — asserted against the frozen
CSVs before any interval is written); each bootstrap rep then resamples H3 cells
with replacement and recomputes every statistic as a ratio of cell-weighted sums.
The SAME cell draw is used for every predictor within a lens, so paired
difference intervals (e.g. fusion − null) are valid.

Blocks: res-8 cells for the core region (res-7 leaves only ~13 blocks there);
res-7 for the as-delivered lens. 2,000 reps, fixed seed. Models are scored from
rq8's frozen out-of-fold scores (rq8_oof_scores_r10.parquet, GIE_DUMP_OOF=1) at
their FROZEN best single cut — no refitting inside the loop, and the cut is not
re-chosen per rep: the interval covers sampling noise around the reported
operating point, not the oracle threshold search.

Outputs: rq9_ci_core.csv (products + k-of-6 rules x r10/20/30 x P/R/F1, plus
Padj and visits/find at their tbl-dial radii), rq9_ci_asdelivered_r10.csv,
rq9_ci_models_r10.csv (incl. paired differences vs the logistic null).

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ9-uncertainty/scripts/rq9_block_bootstrap.py
"""
from __future__ import annotations
import gzip, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..")
POS = (2, 3)
REPS = 2000
SEED = 20260810
RES_CORE, RES_ASD = 8, 7
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
TOL = 6e-4  # frozen CSVs are rounded to 3 dp


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
        if not gp.mapswipe_is_frozen(b.name):
            continue
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            rows = [f["properties"] for f in feats if f["properties"].get("h3")]
            if rows:
                frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= 4].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")["majority"]


def h3_cells(geoms4326, res):
    return np.array([h3.latlng_to_cell(p.y, p.x, res) for p in geoms4326])


def cell_index(*cell_arrays):
    uniq = sorted(set().union(*(set(a) for a in cell_arrays)))
    lut = {c: i for i, c in enumerate(uniq)}
    return lut, len(uniq)


def agg(cells_idx, indicator, ncells):
    return np.bincount(cells_idx, weights=indicator.astype(float), minlength=ncells)


def draw_weights(rng, ncells):
    """REPS draws of ncells cells with replacement, as multiplicity vectors."""
    idx = rng.integers(0, ncells, size=(REPS, ncells))
    flat = (idx + np.arange(REPS)[:, None] * ncells).ravel()
    return np.bincount(flat, minlength=REPS * ncells).reshape(REPS, ncells).astype(float)


def pct(a):
    return float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5))


def check(name, got, frozen):
    if not np.isfinite(frozen):
        return
    if abs(got - frozen) > TOL:
        raise RuntimeError(f"point-estimate mismatch {name}: recomputed {got:.4f} "
                           f"vs frozen {frozen:.4f} — machinery drift, refusing to write CIs")


def main():
    import ocha_stratus as stratus
    rng = np.random.default_rng(SEED)
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    votes = df[list(MEMBERS.values())].sum(axis=1)

    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    all_ext = ext.geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    prod_aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
                 "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
                 "OSU": gp.dissolve_union(gp.osu_aoi()),
                 "UH": uh_aoi(),
                 "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                       "analysed_extent.parquet")),
                 "UNEP": None}
    tasks = mapswipe_tasks()

    def verdicts(sub4326):
        out = np.full(len(sub4326), np.nan)
        for i, p in enumerate(sub4326.geometry):
            for res in (11, 12):
                c = h3.latlng_to_cell(p.y, p.x, res)
                if c in tasks.index:
                    out[i] = float(tasks.loc[c])
                    break
        return out

    # ================= lens 1: core region (rq5b machinery, res-8 blocks) ========
    region = all_ext
    for a in prod_aois.values():
        if a is not None:
            region = region.intersection(a)
    in_reg = bld.geometry.within(region)
    cpts = cems[cems.geometry.within(region)]
    frozen5 = {r: pd.read_csv(os.path.join(
        OUT, "..", "RQ5-ensemble", f"rq5b_six_member{'' if r == 10 else f'_r{r}'}.csv"))
        .set_index("rule") for r in (10, 20, 30)}

    cem_cells = h3_cells(cpts.to_crs(4326).geometry, RES_CORE)
    bld_core = bld[in_reg]
    bld_cells_all = h3_cells(bld_core.to_crs(4326).geometry, RES_CORE)
    lut, nc = cell_index(cem_cells, bld_cells_all)
    cem_idx = np.array([lut[c] for c in cem_cells])
    print(f"core lens: {int(in_reg.sum()):,} buildings, {len(cpts):,} CEMS pts, "
          f"{nc} res-{RES_CORE} blocks")
    W = draw_weights(rng, nc)
    cxy = np.c_[cpts.geometry.x, cpts.geometry.y]
    ct = cKDTree(cxy)

    rules = [(nm, in_reg & (df[col] == 1)) for nm, col in MEMBERS.items()]
    rules += [(f"{k}-of-6", in_reg & (votes >= k)) for k in range(1, 7)]
    rows = []
    for nm, sel in rules:
        fl = bld[sel]
        fxy = np.c_[fl.geometry.x, fl.geometry.y]
        f_cells = np.array([lut[c] for c in h3_cells(fl.to_crs(4326).geometry, RES_CORE)])
        ftree = cKDTree(fxy)
        flags_c = agg(f_cells, np.ones(len(fl)), nc)
        den_c = agg(cem_idx, np.ones(len(cpts)), nc)
        hit10 = None
        for r in (10, 20, 30):
            hit = ct.query(fxy, k=1)[0] <= r          # precision side, per flag
            rec = ftree.query(cxy, k=1)[0] <= r        # recall side, per CEMS point
            if r == 10:
                hit10 = hit
            P = W @ agg(f_cells, hit, nc) / (W @ flags_c)
            R = W @ agg(cem_idx, rec, nc) / (W @ den_c)
            F1 = np.where((P + R) > 0, 2 * P * R / (P + R), 0.0)
            fz = frozen5[r].loc[nm]
            p0, r0 = float(hit.mean()), float(rec.mean())
            f0 = 2 * p0 * r0 / (p0 + r0) if (p0 + r0) > 0 else 0.0
            check(f"core {nm} P r{r}", p0, fz["P_cems"])
            check(f"core {nm} R r{r}", r0, fz["R_cems"])
            for metric, point, boot in (("P", p0, P), ("R", r0, R), ("F1", f0, F1)):
                lo, hi = pct(boot)
                rows.append(dict(lens="core", rule=nm, radius=r, metric=metric,
                                 point=round(point, 3), lo=round(lo, 3), hi=round(hi, 3)))
            if r == 30:
                with np.errstate(divide="ignore", invalid="ignore"):
                    visits = (W @ flags_c) / (W @ agg(cem_idx, rec, nc))
                v0 = len(fl) / max(int(rec.sum()), 1)
                lo, hi = pct(visits)
                rows.append(dict(lens="core", rule=nm, radius=30, metric="visits_per_find",
                                 point=round(v0, 2), lo=round(lo, 2), hi=round(hi, 2)))
        # crowd-adjusted precision, r10 (tbl-dial column)
        v = verdicts(fl[~hit10].to_crs(4326)) if (~hit10).any() else np.array([])
        fp_c = agg(f_cells[~hit10], np.ones(int((~hit10).sum())), nc)
        jud_c = agg(f_cells[~hit10], ~np.isnan(v), nc)
        dmg_c = agg(f_cells[~hit10], v == 1, nc)
        with np.errstate(divide="ignore", invalid="ignore"):
            conf = (W @ dmg_c) / (W @ jud_c)
            padj = (W @ agg(f_cells, hit10, nc) + (W @ fp_c) * conf) / (W @ flags_c)
        conf0 = float((v == 1).sum() / max((~np.isnan(v)).sum(), 1))
        p0 = float(hit10.mean())
        padj0 = (hit10.sum() + (~hit10).sum() * conf0) / len(fl)
        check(f"core {nm} Padj", padj0, frozen5[10].loc[nm]["P_crowd_adj"])
        lo, hi = pct(padj)
        rows.append(dict(lens="core", rule=nm, radius=10, metric="P_crowd_adj",
                         point=round(float(padj0), 3), lo=round(lo, 3), hi=round(hi, 3)))
        print(f"  core {nm}: done ({len(fl):,} flags)")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "rq9_ci_core.csv"), index=False)
    print("wrote rq9_ci_core.csv")

    # ============ lens 2: as-delivered (rq2i machinery, res-7 blocks) ============
    frozen_i = pd.read_csv(os.path.join(OUT, "..", "RQ2-cems-footprint-points",
                                        "rq2i_per_aoi_scorecard.csv"))
    frozen_i = (frozen_i[frozen_i.aoi == "ALL (as delivered)"]
                .drop_duplicates("product").set_index("product"))
    cem_cells7 = h3_cells(cems[cems.geometry.within(all_ext)].to_crs(4326).geometry, RES_ASD)
    bld_ext = bld[bld.geometry.within(all_ext)]
    lut7, nc7 = cell_index(cem_cells7, h3_cells(bld_ext.to_crs(4326).geometry, RES_ASD))
    print(f"as-delivered lens: {nc7} res-{RES_ASD} blocks")
    W7 = draw_weights(rng, nc7)
    rows = []
    for nm, col in MEMBERS.items():
        reg = all_ext if prod_aois[nm] is None else all_ext.intersection(prod_aois[nm])
        fl = bld[bld.geometry.within(reg) & (df[col] == 1)]
        ca = cems[cems.geometry.within(reg)]
        fxy, caxy = np.c_[fl.geometry.x, fl.geometry.y], np.c_[ca.geometry.x, ca.geometry.y]
        hit = cKDTree(caxy).query(fxy, k=1)[0] <= 10
        rec = cKDTree(fxy).query(caxy, k=1)[0] <= 10
        f_cells = np.array([lut7[c] for c in h3_cells(fl.to_crs(4326).geometry, RES_ASD)])
        c_cells = np.array([lut7[c] for c in h3_cells(ca.to_crs(4326).geometry, RES_ASD)])
        P = W7 @ agg(f_cells, hit, nc7) / (W7 @ agg(f_cells, np.ones(len(fl)), nc7))
        R = W7 @ agg(c_cells, rec, nc7) / (W7 @ agg(c_cells, np.ones(len(ca)), nc7))
        p0, r0 = float(hit.mean()), float(rec.mean())
        check(f"asd {nm} P", p0, frozen_i.loc[nm]["P_cems"])
        check(f"asd {nm} R", r0, frozen_i.loc[nm]["R_cems"])
        for metric, point, boot in (("P", p0, P), ("R", r0, R)):
            lo, hi = pct(boot)
            rows.append(dict(lens="as-delivered", rule=nm, radius=10, metric=metric,
                             point=round(point, 3), lo=round(lo, 3), hi=round(hi, 3)))
        print(f"  as-delivered {nm}: done")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "rq9_ci_asdelivered_r10.csv"), index=False)
    print("wrote rq9_ci_asdelivered_r10.csv")

    # ====== lens 3: models at frozen cuts (rq8 frame, frozen OOF, res-8) =========
    oof_path = os.path.join(OUT, "..", "RQ8-learned-fusion", "rq8_oof_scores_r10.parquet")
    if not os.path.exists(oof_path):
        raise RuntimeError("rq8_oof_scores_r10.parquet missing — run rq8_learned_fusion.py "
                           "with GIE_DUMP_OOF=1 first (frozen OOF scores are required; "
                           "this script must not refit)")
    md = pd.read_parquet(oof_path)
    frozen8 = pd.read_csv(os.path.join(OUT, "..", "RQ8-learned-fusion",
                                       "rq8_best_f1_r10.csv")).set_index("predictor")
    y = md.y.to_numpy()
    cells8 = np.array([h3.latlng_to_cell(la, lo, RES_CORE)
                       for la, lo in zip(md.lat, md.lon)])
    lut8, nc8 = cell_index(cells8)
    b_idx = np.array([lut8[c] for c in cells8])
    print(f"models lens: {len(md):,} buildings, {nc8} res-{RES_CORE} blocks")
    W8 = draw_weights(rng, nc8)
    pos_c = agg(b_idx, y == 1, nc8)
    vote_col = md[[c for c in md.columns if c.startswith("flag_")]].sum(axis=1).to_numpy()

    def frozen_cut(name, score):
        """Reproduce rq8's best-F1 cut from the frozen scores and assert it."""
        from sklearn.metrics import precision_recall_curve
        p, r, thr = precision_recall_curve(y, score)
        f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)
        i = int(np.argmax(f1))
        t = thr[i] if i < len(thr) else thr[-1]
        check(f"models {name} F1@cut", float(f1[i]), frozen8.loc[name]["f1"])
        return t

    preds = [(f"{nm} (as shipped)", md[f"flag_{nm}"].to_numpy(), 1.0)
             for nm in MEMBERS if f"flag_{nm}" in md]
    for name, col in (("geography null (logistic)", "null_logit"),
                      ("geography null (rand. forest)", "null_rf"),
                      ("weighted fusion", "fusion_logit")):
        preds.append((name, md[col].to_numpy(), frozen_cut(name, md[col].to_numpy())))
    preds.append(("flat k-of-6 voting", vote_col,
                  frozen_cut("flat k-of-6 voting", vote_col)))

    rows, f1_boot = [], {}
    for name, score, cut in preds:
        sel = score >= cut
        tp_c = agg(b_idx, sel & (y == 1), nc8)
        fl_c = agg(b_idx, sel, nc8)
        with np.errstate(divide="ignore", invalid="ignore"):
            P = W8 @ tp_c / (W8 @ fl_c)
            R = W8 @ tp_c / (W8 @ pos_c)
            F1 = np.where((P + R) > 0, 2 * P * R / (P + R), 0.0)
        f1_boot[name] = F1
        p0 = float((sel & (y == 1)).sum() / max(sel.sum(), 1))
        r0 = float((sel & (y == 1)).sum() / max((y == 1).sum(), 1))
        f0 = 2 * p0 * r0 / (p0 + r0) if (p0 + r0) > 0 else 0.0
        base = name.replace(" (as shipped)", "")
        if base in MEMBERS:
            check(f"models {base} P", p0, frozen8.loc[base]["precision"])
        for metric, point, boot in (("P", p0, P), ("R", r0, R), ("F1", f0, F1)):
            lo, hi = pct(boot)
            rows.append(dict(predictor=name, metric=metric, point=round(point, 3),
                             lo=round(lo, 3), hi=round(hi, 3)))
        print(f"  models {name}: done")

    # paired differences vs the logistic null — same cell draws, so valid
    null = f1_boot["geography null (logistic)"]
    for name in f1_boot:
        if name == "geography null (logistic)":
            continue
        d_ = f1_boot[name] - null
        lo, hi = pct(d_)
        rows.append(dict(predictor=f"{name} − null (logit)", metric="F1_diff",
                         point=round(float(np.median(d_)), 3),
                         lo=round(lo, 3), hi=round(hi, 3)))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "rq9_ci_models_r10.csv"), index=False)
    print("wrote rq9_ci_models_r10.csv")


if __name__ == "__main__":
    main()
