"""RQ4 — incorporate UNEP debris via enclosed hard-hit admin units; 4-way comparison.

UNEP debris has NO analysed AOI (detected-only), so it can't be bounded by an AOI intersection.
Fix (as discussed): restrict to adm3 (parroquia) units that are (a) essentially fully inside CEMS's
analysed extent [CEMS is complete there] and (b) hard-hit [so we can assume UNEP covered the whole
unit]. Within those units the edge-of-analysis ambiguity is negligible. STATED ASSUMPTION: UNEP
fully covers the selected enclosed hard-hit units.

Bonus: this enclosed-admin region is a COMMON coverage for ALL sources, so MS / IMPACT v2 / OSU /
UNEP are compared on identical ground (fixes the 'different AOIs aren't comparable' caveat).

Dual-anchor recall/precision/F1 (RQ0) + H3 res-8 rank agreement, r=10 m, CEMS positive {2,3}.
Run: uv run --group etl python exploratory/paper/artefacts/RQ4-unep-enclosed-admin/scripts/rq4_enclosed_admin.py
"""
from __future__ import annotations
import os, sys
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)
R = 10
HIT_THRESH = 30      # hard-hit adm3 = >=30 CEMS damage+destroyed points
# NB: we do NOT gate on the fraction of the parroquia AREA inside the CEMS extent — adm3 units are
# huge and mostly mountain (no buildings). Enclosure is applied by intersecting each hard-hit unit
# with the CEMS analysed extent (the built-up strip CEMS assessed); UNEP is ASSUMED to cover that
# strip in these hard-hit districts. That assumption is the RQ4 caveat.


def sources():
    ms = gp.microsoft()
    return {
        "Microsoft": gp.to_metric(ms),
        "IMPACT v2": gp.to_metric(gp.impact_v2()),
        "OSU": gp.to_metric(gp.osu()),
        "UNEP debris": gp.to_metric(gp.unep()[gp.unep().debris_tonnes > 0]),
    }


def h3_counts(gdf_metric, region, res=8):
    import h3
    sub = gdf_metric[gdf_metric.geometry.representative_point().within(region)]
    if not len(sub):
        return pd.Series(dtype=int)
    ll = sub.to_crs(4326).geometry.representative_point()
    return pd.Series([h3.latlng_to_cell(p.y, p.x, res) for p in ll]).value_counts()


def main():
    adm = gp.to_metric(gp.codab(3))[["adm3_id", "adm3_name", "adm2_name", "geometry"]].copy()
    adm["geometry"] = adm.geometry.make_valid()
    cems_all = gp.to_metric(gp.cems_points())
    cems = cems_all[cems_all.damage_class.isin(POS)]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712

    # CEMS damage count per adm3 + area fraction inside CEMS extent
    j = gpd.sjoin(cems[["geometry"]], adm, predicate="within", how="inner")
    cnt = j.groupby("adm3_id").size().rename("cems_pts")
    adm = adm.join(cnt, on="adm3_id").fillna({"cems_pts": 0})
    adm["area_frac_in_ext"] = adm.geometry.intersection(ext_latest).area / adm.geometry.area

    cand = adm[adm.cems_pts > 0].sort_values("cems_pts", ascending=False)
    print("== adm3 units with CEMS damage (candidate enclosed units) ==")
    print(cand[["adm3_name", "adm2_name", "cems_pts", "area_frac_in_ext"]].to_string(index=False))

    enclosed = adm[adm.cems_pts >= HIT_THRESH]
    print(f"\nHARD-HIT units (cems>={HIT_THRESH}): {len(enclosed)} -> {enclosed.adm3_name.tolist()}")
    # region = built-up strip CEMS assessed within the hard-hit districts (UNEP assumed to cover it)
    region = enclosed.geometry.make_valid().union_all().intersection(ext_latest)
    cems_in = cems[cems.within(region)]
    print(f"region area: {region.area/1e6:.1f} km2 | CEMS damage points in region: {len(cems_in)}")

    rows, scatter = [], {}
    cems_h = h3_counts(cems, region).rename("cems")
    for name, foot in sources().items():
        foot_in = foot[foot.geometry.representative_point().within(region)]
        tp_r, n_pts = gp.match_rate(cems_in, foot_in, R)
        tp_p, n_prod = gp.match_rate(foot_in, cems_in, R)
        rec = tp_r / n_pts if n_pts else float("nan")
        prec = tp_p / n_prod if n_prod else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float("nan")
        ph = h3_counts(foot, region).rename("pdmg")
        d = pd.concat([cems_h, ph], axis=1).fillna(0)
        both = d[(d.cems > 0) | (d.pdmg > 0)]
        rho, _ = spearmanr(both.cems, both.pdmg) if len(both) > 2 else (float("nan"), 0)
        overdet = n_prod / len(cems_in) if len(cems_in) else float("nan")
        rows.append(dict(source=name, dmg_in_region=n_prod, recall=round(rec, 3),
                         precision=round(prec, 3), f1=round(f1, 3),
                         overdet_x=round(overdet, 1), rank_rho=round(rho, 3)))
        scatter[name] = (both.cems.values, both.pdmg.values, rho)
        print(f"  {name:12s} dmg={n_prod:6d} R={rec:.3f} P={prec:.3f} F1={f1:.3f} "
              f"overdet={overdet:.1f}x rank_rho={rho:.3f}")

    df = pd.DataFrame(rows)
    csv = os.path.join(os.path.dirname(__file__), "..", "rq4_enclosed_summary.csv")
    df.to_csv(csv, index=False)
    print("\n", df.to_string(index=False), "\nwrote", csv)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    df.set_index("source")[["recall", "precision", "f1"]].plot.bar(ax=ax[0], rot=20)
    ax[0].set_title(f"4-way vs CEMS points, enclosed hard-hit admin (r={R} m)"); ax[0].set_ylim(0, 1)
    df.set_index("source")[["rank_rho"]].plot.bar(ax=ax[1], rot=20, color="teal", legend=False)
    ax[1].set_title("H3 res-8 rank agreement with CEMS"); ax[1].set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "rq4_enclosed_4way.png"), dpi=130)
    print("wrote figs/rq4_enclosed_4way.png")


if __name__ == "__main__":
    main()
