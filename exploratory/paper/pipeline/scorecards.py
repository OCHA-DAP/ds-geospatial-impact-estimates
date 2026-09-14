"""Scorecards: every precision/recall-type number in the brief, as rows of the results table.

One module replaces rq5b, rq2q, rq2r, rq2i, rq2s, rq2k, rq2l, rq2o and rq2_chatmap. Each
function below is one lens or region; all of them use paperlib's definitions, so the frame
(ADR-0030), the crowd rule (ADR-0031) and the regions are decided once.

Rows: region, lens, radius, predictor, metric, value, source.
Usage: python scorecards.py [--only core_points,...]  -> results_scorecards.csv beside this file
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as pl  # noqa: E402
from paperlib import gp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = "pipeline/scorecards.py"
SHORT = list(pl.PRODUCTS)                         # MS IMPACT OSU UH LIST UNEP
MIN_CEMS_FOR_RECALL = 20                          # per-AOI recall suppressed below this
SPLIT_LON = -67.03                                # Microsoft's scene boundary (west/east strip)
FIELD_RADII = (10, 20, 50)
FIELD_GRADES = ("complete", "significant", "minimal")


def rows(region, lens, radius, predictor, **metrics):
    return [dict(region=region, lens=lens, radius=radius, predictor=predictor, metric=m, value=v, source=SOURCE)
            for m, v in metrics.items() if v is not None and not (isinstance(v, float) and np.isnan(v))]


def r3(x):
    return round(float(x), 3)


# ---------------------------------------------------------------- core region
def core_points():
    """Core, points lens, r = 10/20/30: products, pairs, k-of-6 (rq5b); field recall at 20 m."""
    b, core, ref = pl.buildings(), pl.core_region(), pl.reference("floor")
    inb = b[pl.in_region(b, core)]
    ref = ref[ref.geometry.within(core)]
    fld = pl.field_points(); fld = fld[fld.geometry.within(core)]
    out = []
    for name, mask in pl.predictors(inb).items():
        fl = inb[mask]
        nf, dfld = gp.match_rate(fld, fl, pl.FIELD_R)
        rf = round(nf / dfld, 2) if dfld else np.nan
        for r in pl.RADII:
            s = pl.score(fl, ref, r)
            out += rows("core", "points", r, name, P=r3(s["P"]), R=r3(s["R"]), F1=r3(s["F1"]), n_flags=s["n_flags"], R_field20=rf)
    return out


def core_crowd():
    """Core, r = 10: measured crowd credit per predictor (rq5b's crowd columns, ADR-0031)."""
    b, core, ref = pl.buildings(), pl.core_region(), pl.reference("floor")
    inb = b[pl.in_region(b, core)]
    ref = ref[ref.geometry.within(core)]
    out = []
    for name, mask in pl.predictors(inb).items():
        c = pl.crowd_credit(inb[mask], ref, 10)
        out += rows("core", "crowd", 10, name, P_crowd=r3(c["P_crowd"]), crowd_cov=round(c["crowd_cov"], 2), fp_crowd_damaged=round(c["fp_crowd_damaged"], 2))
    return out


def core_possibly():
    """Core, r = 10, reference widened to CEMS 'possibly damaged' (rq2q incl_possibly)."""
    b, core = pl.buildings(), pl.core_region()
    inb = b[pl.in_region(b, core)]
    ref = pl.reference("grade"); ref = ref[ref.geometry.within(core)]
    out = []
    preds = pl.predictors(inb)
    for name in SHORT + [f"{k}-of-6" for k in range(1, 7)]:
        s = pl.score(inb[preds[name]], ref, 10)
        out += rows("core", "points+possibly", 10, name, P=r3(s["P"]), R=r3(s["R"]), F1=r3(s["F1"]), n_flags=s["n_flags"], n_ref=s["n_ref"])
    return out


def core_bounds():
    """Core, r = 10, the precision ladder per product (rq2r): floor, +possibly, +crowd, both."""
    b, core = pl.buildings(), pl.core_region()
    inb = b[pl.in_region(b, core)].reset_index(drop=True)
    hit23 = gp.within_r(inb, pl.reference("floor"), 10)
    hit123 = gp.within_r(inb, pl.reference("grade"), 10)
    hit1 = gp.within_r(inb, gp.to_metric(gp.cems_points()).query("damage_class == 1")[["geometry"]], 10)
    cv = pl.crowd_verdicts(inb)
    crowd_dmg = cv == 1
    voted = ~np.isnan(cv)
    out = []
    for p, col in pl.PRODUCTS.items():
        fl = inb[col].to_numpy() == 1
        fp23 = fl & ~hit23
        cov = float(voted[fp23].mean()) if fp23.any() else np.nan
        cc = fp23 & crowd_dmg
        near1 = float(hit1[cc].mean()) if cc.any() else np.nan
        out += rows("core", "bounds", 10, p, P_floor=r3(hit23[fl].mean()), P_grade=r3(hit123[fl].mean()),
                    P_crowd=r3((hit23 | crowd_dmg)[fl].mean()), P_upper=r3((hit123 | crowd_dmg)[fl].mean()),
                    crowd_cov=round(cov, 2), crowd_fp_near_class1=round(near1, 2) if near1 == near1 else np.nan)
    return out


def core_field_union():
    """Core, r = 10: precision/recall against CEMS alone vs CEMS ∪ ChatMap (rq2k)."""
    b, core = pl.buildings(), pl.core_region()
    inb = b[pl.in_region(b, core)]
    cpts = pl.reference("floor"); cpts = cpts[cpts.geometry.within(core)][["geometry"]]
    fpts = pl.field_points(); fpts = fpts[fpts.geometry.within(core)][["geometry"]]
    union = gpd.GeoDataFrame(geometry=pd.concat([cpts.geometry, fpts.geometry], ignore_index=True), crs=pl.METRIC_CRS)
    out = []
    for p, col in pl.PRODUCTS.items():
        fl = inb[inb[col] == 1]
        pc, pu = gp.within_r(fl, cpts, 10).mean(), gp.within_r(fl, union, 10).mean()
        rc, ru = gp.within_r(cpts, fl, 10).mean(), gp.within_r(union, fl, 10).mean()
        out += rows("core", "field-union", 10, p, P_cems=r3(pc), P_union=r3(pu), R_cems=r3(rc), R_union=r3(ru),
                    P_rel_gain=round(100 * (pu / pc - 1)), R_rel_change=round(100 * (ru / rc - 1)))
    return out


def core_grade_recall():
    """Core, r = 10: precision and recall split by CEMS grade, damaged (2) vs destroyed (3) (rq2l)."""
    b, core = pl.buildings(), pl.core_region()
    inb = b[pl.in_region(b, core)]
    cems = gp.to_metric(gp.cems_points()); cems = cems[cems.geometry.within(core)]
    dam, des = cems[cems.damage_class == 2][["geometry"]], cems[cems.damage_class == 3][["geometry"]]
    out = []
    for p, col in pl.PRODUCTS.items():
        fl = inb[inb[col] == 1]
        out += rows("core", "grade-recall", 10, p, P_vs_damaged=r3(gp.within_r(fl, dam, 10).mean()), P_vs_destroyed=r3(gp.within_r(fl, des, 10).mean()),
                    R_of_damaged=r3(gp.within_r(dam, fl, 10).mean()), R_of_destroyed=r3(gp.within_r(des, fl, 10).mean()))
    return out


# ---------------------------------------------------------------- as delivered and per AOI
def as_delivered():
    """Every CEMS AOI and the pooled as-delivered frame, per product, r = 10 (rq2i), with
    measured crowd credit. Recall is suppressed where the AOI holds < MIN_CEMS_FOR_RECALL points."""
    b = pl.buildings()
    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    cems = pl.reference("floor")
    aois = dict(pl.product_aois()); aois["UNEP"] = None
    groups = [("asd", ext)] + [(a, s) for a, s in ext.groupby("aoi_name")]
    out = []
    for region_name, sub in groups:
        region = sub.geometry.make_valid().union_all()
        cpts = cems[cems.geometry.within(region)]
        for p, col in pl.PRODUCTS.items():
            reg = region if aois[p] is None else region.intersection(aois[p])
            if reg.is_empty:
                continue
            inb = b[pl.in_region(b, reg)]
            if len(inb) < 50:
                continue
            fl = inb[inb[col] == 1]
            ca = cpts[cpts.geometry.within(reg)]
            m = dict(n_bld=len(inb), n_flags=len(fl), flag_share=r3(len(fl) / len(inb)), n_cems=len(ca))
            if len(fl) and len(ca):
                m["P"] = r3(gp.within_r(fl, ca, 10).mean())
                m["R"] = r3(gp.within_r(ca, fl, 10).mean()) if len(ca) >= MIN_CEMS_FOR_RECALL else np.nan
            out += rows(region_name, "points", 10, p, **m)
            if len(fl):
                c = pl.crowd_credit(fl, ca, 10)
                if not (c["fp_crowd_damaged"] == c["fp_crowd_damaged"]):   # no reviewed unmatched flag: nothing to credit
                    c["P_crowd"] = np.nan
                out += rows(region_name, "crowd", 10, p, P_crowd=r3(c["P_crowd"]) if c["P_crowd"] == c["P_crowd"] else np.nan,
                            crowd_cov=round(c["crowd_cov"], 2) if c["crowd_cov"] == c["crowd_cov"] else np.nan,
                            fp_crowd_damaged=round(c["fp_crowd_damaged"], 2) if c["fp_crowd_damaged"] == c["fp_crowd_damaged"] else np.nan)
    return out


def flag_totals():
    """Total flags per product on the shared base vs flags inside any CEMS extent (rq2s)."""
    b = pl.buildings()
    ext = pl.cems_extent_latest()
    aois = dict(pl.product_aois()); aois["UNEP"] = None
    out = []
    for p, col in pl.PRODUCTS.items():
        fl = b[col].to_numpy() == 1
        reg = ext if aois[p] is None else ext.intersection(aois[p])   # the as-delivered scoring region
        total, inside = int(fl.sum()), int((fl & pl.in_region(b, reg)).sum())
        out += rows("all", "flags", None, p, total_flags=total, in_cems_extent=inside, share_outside=r3(1 - inside / total))
    return out


def west_strip():
    """Caraballeda split at Microsoft's scene boundary: UH and Microsoft, west vs east (rq2o)."""
    b = pl.buildings()
    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    cara = ext[ext.aoi_name == "Caraballeda"].geometry.make_valid().union_all()
    cems = pl.reference("floor")
    out = []
    for p in ("UH", "MS"):
        reg = cara.intersection(pl.product_aois()[p])
        inb = b[pl.in_region(b, reg)]
        lon = pl.location(inb).to_crs(4326).x
        ca = cems[cems.geometry.within(reg)]
        ca_lon = ca.geometry.to_crs(4326).x
        for side, mask, cmask in (("west", lon < SPLIT_LON, ca_lon < SPLIT_LON), ("east", lon >= SPLIT_LON, ca_lon >= SPLIT_LON)):
            sub, c = inb[mask.to_numpy()], ca[cmask.to_numpy()]
            fl = sub[sub[pl.PRODUCTS[p]] == 1]
            P = r3(gp.within_r(fl, c, 10).mean()) if len(fl) and len(c) else np.nan
            out += rows(f"strip-{side}", "points", 10, p, n_bld=len(sub), n_flags=len(fl), flag_share=r3(len(fl) / len(sub)), n_cems=len(c), P=P)
    return out


# ---------------------------------------------------------------- field reference (ChatMap)
def field_recall():
    """Share of ChatMap field reports with a flag within r, per product inside its own AOI,
    for the union rules, and for CEMS itself (rq2_chatmap). Not-evaluated products (fAIr,
    DISHA) get a raw hit-rate over all field points."""
    b = gp.buildings(columns=[*pl.PRODUCTS.values(), "hot_dmg", "disha_dmg"])
    for c in [*pl.PRODUCTS.values(), "hot_dmg", "disha_dmg"]:
        b[c] = (b[c].to_numpy(dtype="float64", na_value=0.0) == 1).astype("int64")
    field = pl.field_points()
    cems_region, core = pl.cems_extent_latest(), pl.core_region()
    aois = pl.product_aois()
    names = {"MS": "MS", "IMPACT": "IMPACT v2", "OSU": "OSU", "UH": "UH", "LIST": "LIST"}
    entries = [(names[p], b[b[pl.PRODUCTS[p]] == 1], aois[p]) for p in names]
    entries.append(("UNEP debris (core region)", b[b["debris_dmg"] == 1], core))
    entries.append(("CEMS {2,3}", pl.reference("floor"), cems_region))
    votes4 = b[["ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"]].sum(axis=1)
    quad = aois["MS"]
    for a in ("IMPACT", "OSU", "UH"):
        quad = quad.intersection(aois[a])
    for k in (1, 2, 3):
        entries.append((f"≥{k}-of-4 votes", b[votes4 >= k], quad))
    votes6 = b[list(pl.PRODUCTS.values())].sum(axis=1)
    for k in (1, 2):
        entries.append((f"≥{k}-of-6 votes (core region)", b[votes6 >= k], core))
    out = []
    for nm, flagged, region in entries:
        fin = field[field.geometry.within(region)]
        if not len(fin):
            continue
        m = {}
        for r in FIELD_RADII:
            n, d = gp.match_rate(fin, flagged, r)
            out += rows("field", "field", r, nm, R=round(n / d, 2))
        m["n_field"] = len(fin)
        for gr in FIELD_GRADES:
            sub = fin[fin.damaged == gr]
            if len(sub) >= 5:
                n, d = gp.match_rate(sub, flagged, 20)
                m[f"R_{gr}"] = round(n / d, 2); m[f"n_{gr}"] = len(sub)
        out += rows("field", "field", 20, nm, **m)
    for nm, col in (("HOT fAIr", "hot_dmg"), ("DISHA", "disha_dmg")):
        n, d = gp.match_rate(field, b[b[col] == 1], 20)
        out += rows("field", "field", 20, f"{nm} (detected-only)", R=round(n / d, 2), n_field=d)
    return out


PARTS = {f.__name__: f for f in (core_points, core_crowd, core_possibly, core_bounds, core_field_union, core_grade_recall,
                                 as_delivered, flag_totals, west_strip, field_recall)}


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    out = []
    for name, fn in PARTS.items():
        if only and name not in only:
            continue
        print(f"== {name}", flush=True)
        out += fn()
    res = pd.DataFrame(out)
    path = os.path.join(HERE, "results_scorecards.csv")
    if only and os.path.exists(path):  # partial run: replace only the parts recomputed
        old = pd.read_csv(path)
        key = ["region", "lens", "radius", "predictor", "metric"]
        res = pd.concat([old.merge(res[key].drop_duplicates(), on=key, how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge"), res])
    res.to_csv(path, index=False)
    print(f"results_scorecards.csv: {len(res)} rows")


if __name__ == "__main__":
    main()
