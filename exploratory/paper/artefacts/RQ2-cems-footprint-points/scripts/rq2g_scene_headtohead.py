"""RQ2g — same-area scene head-to-head: Vantor Jun-25 vs Planet Jun-26 (Catia La Mar overlap).

Microsoft's merge resolved cross-scene conflicts "favoring Planet" without independent
validation of either scene. Their per-scene HDX GeoPackages let us test it: on the buildings
BOTH scenes saw, score each scene's raw calls independently against (a) CEMS latest {2,3}
(dual-anchor r=10 m) and (b) the MapSwipe crowd (majority of >=4 votes on the ~50 m cell).
Also adjudicate the conflict set itself (V-flagged & P-intact) — was the tie-break right?

Inputs (scratchpad, downloaded from HDX 2026-07-17):
  ms_scenes/vantor_25.gpkg   (predicted_damage_catia_la_mar_footprints)
  ms_scenes/planet_east.gpkg (predicted_damage_East-Catia-La-Mar-Skysat-final)

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2g_scene_headtohead.py
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

S = ("/private/tmp/claude-501/-Users-zackarno-Documents-CHD-repos-ds-geospatial-impact-estimates"
     "/6a2963d5-ef5a-4570-85b7-87c84e12fb21/scratchpad/ms_scenes")
HERE = os.path.dirname(__file__)
POS = (2, 3)
R = 10


def crowd_lookup():
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE")
    frames = []
    for b in cc.list_blobs(name_starts_with=pref):
        if not gp.mapswipe_is_frozen(b.name):
            continue  # post-freeze round-2 re-vote (see gie_paper.MAPSWIPE_POSTFREEZE)
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            rows = [f["properties"] for f in feats if f["properties"].get("h3")]
            if rows:
                frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= 4].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")["majority"]


def crowd_verdicts(gdf, tasks):
    ll = gdf.to_crs(4326).geometry.representative_point()
    out = []
    for p in ll:
        v = np.nan
        for res in (11, 12):
            c = h3.latlng_to_cell(p.y, p.x, res)
            if c in tasks.index:
                v = int(tasks.loc[c])
                break
        out.append(v)
    return pd.Series(out, index=gdf.index)


def main():
    v = gpd.read_file(f"{S}/vantor_25.gpkg")
    p = gpd.read_file(f"{S}/planet_east.gpkg")
    # common buildings: HASTE uses one footprint layer -> match by id if shared, else centroid
    common_ids = set(v.id) & set(p.id)
    print(f"Vantor {len(v):,} | Planet {len(p):,} | shared ids: {len(common_ids):,}")
    if len(common_ids) > 1000:
        v = v.set_index("id").loc[sorted(common_ids)]
        p = p.set_index("id").loc[sorted(common_ids)]
    else:  # centroid match <= 5 m
        vc, pc = v.geometry.centroid, p.geometry.centroid
        t = cKDTree(np.c_[pc.x, pc.y])
        d, i = t.query(np.c_[vc.x, vc.y], k=1)
        keep = d <= 5
        v = v[keep].reset_index(drop=True)
        p = p.iloc[i[keep]].reset_index(drop=True)
        print(f"centroid-matched pairs (<=5 m): {keep.sum():,}")

    both = pd.DataFrame({"v_dmg": v.damaged.to_numpy(), "p_dmg": p.damaged.to_numpy()})
    geom = gpd.GeoDataFrame(both, geometry=v.geometry.values, crs=v.crs)
    print(f"\noverlap universe: {len(geom):,} buildings")
    print(f"Vantor flags {int(both.v_dmg.sum()):,} ({both.v_dmg.mean():.1%}) | "
          f"Planet flags {int(both.p_dmg.sum()):,} ({both.p_dmg.mean():.1%})")
    conf_vp = geom[(both.v_dmg == 1) & (both.p_dmg == 0)]
    conf_pv = geom[(both.p_dmg == 1) & (both.v_dmg == 0)]
    agree = geom[(both.v_dmg == 1) & (both.p_dmg == 1)]
    print(f"conflicts: V-dmg/P-intact {len(conf_vp):,} | P-dmg/V-intact {len(conf_pv):,} | "
          f"both-dmg {len(agree):,}")

    # CEMS scoring on the common stock
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    cent = geom.geometry.centroid
    bt = cKDTree(np.c_[cent.x, cent.y])
    cd, _ = bt.query(np.c_[cems.geometry.x, cems.geometry.y], k=1)
    cpts = cems[cd <= 30]  # CEMS points sitting on the common stock
    print(f"CEMS {{2,3}} points on the overlap stock: {len(cpts):,}")

    tasks = crowd_lookup()
    rows = []
    for nm, col in (("Vantor Jun-25", "v_dmg"), ("Planet Jun-26", "p_dmg")):
        flags = geom[both[col] == 1]
        fc = flags.geometry.centroid
        ct = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
        fd, _ = ct.query(np.c_[fc.x, fc.y], k=1)
        prec = (fd <= R).mean() if len(flags) else np.nan
        ft = cKDTree(np.c_[fc.x, fc.y]) if len(flags) else None
        rd, _ = ft.query(np.c_[cpts.geometry.x, cpts.geometry.y], k=1)
        rec = (rd <= R).mean() if len(cpts) else np.nan
        f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0
        cv = crowd_verdicts(flags, tasks)
        rows.append(dict(scene=nm, flags=len(flags),
                         P_cems=round(prec, 3), R_cems=round(rec, 3), F1=round(f1, 3),
                         crowd_damaged=round((cv == 1).mean(), 2),
                         crowd_no=round((cv == 0).mean(), 2),
                         crowd_cov=round(cv.notna().mean(), 2)))
        print(rows[-1])

    # adjudicate the conflict set (the ~overruled flags)
    for nm, sub in (("V-dmg/P-intact (overruled)", conf_vp), ("both-damaged", agree)):
        cv = crowd_verdicts(sub, tasks)
        fc = sub.geometry.centroid
        ct = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
        fd, _ = ct.query(np.c_[fc.x, fc.y], k=1) if len(sub) else (np.array([]), None)
        print(f"{nm}: n={len(sub):,} | CEMS<=10m: {(fd <= R).mean():.1%} | "
              f"crowd damaged {(cv == 1).mean():.0%} / no {(cv == 0).mean():.0%} "
              f"(coverage {cv.notna().mean():.0%})")

    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq2g_scene_headtohead.csv"), index=False)
    print("wrote rq2g_scene_headtohead.csv")


if __name__ == "__main__":
    main()
