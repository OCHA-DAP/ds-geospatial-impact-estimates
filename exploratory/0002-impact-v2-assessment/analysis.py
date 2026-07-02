"""Exploratory 0002 — verify IMPACT Sentinel-1 damage v2 before it supersedes v1.

Findings: findings.md (same folder). Feeds ADR-0015.

Reads the v2 GeoPackages from bronze and checks the assumptions behind the
supersede: footprints == our Overture base, damaged-only, no damage classes, AOI
envelops v1, and that the "duplicate id" is a blank on distinct national-source
buildings (not duplicate buildings).

Run (needs the dev-lake env: GIE_BLOB_ACCOUNT_PREFIX + DSCI_AZ_BLOB_DEV_SAS):
  uv run --group etl python exploratory/0002-impact-v2-assessment/analysis.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd
import numpy as np
import ocha_stratus as stratus
from shapely import STRtree, from_wkb

from gie import db
from gie.config import load_settings

SRC, ADM0 = "impact_initiatives", "VE"
DMG_GPKG = "IMPACT_VEN_Earthquake_Sentinel1_damaged_20260625_v2.gpkg"
AOI_GPKG = "IMPACT_VEN_Earthquake_analyzed_area_20260625_v2.gpkg"


def read_bronze_gpkg(settings, name):
    bp = settings.blob_path("bronze", f"source={SRC}", f"adm0={ADM0}", name)
    raw = stratus.load_blob_data(bp, stage="dev", container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        return gpd.read_file(tmp)
    finally:
        os.unlink(tmp)


def main() -> None:
    s = load_settings("dev")
    con = db.connect(s)
    dmg = read_bronze_gpkg(s, DMG_GPKG)  # EPSG:32619
    aoi = read_bronze_gpkg(s, AOI_GPKG)
    n = len(dmg)
    print(f"v2 damaged rows: {n:,} | AOI area {aoi.geometry.area.sum() / 1e6:,.0f} km2")

    # 1) the "duplicate id" is a blank on distinct national-source buildings ----
    vc = dmg["id"].value_counts()
    blank = vc.index[0]
    print(f"\n[1] id: {dmg['id'].nunique():,} unique | most-repeated={blank!r} "
          f"x{int(vc.iloc[0]):,} | bdg_id unique {dmg['bdg_id'].nunique():,} (valid count)")
    print(f"    source of the blank-id rows: "
          f"{dmg[dmg['id'].eq(blank)]['source'].value_counts().to_dict()}")

    # 2) damaged-only + the >=50% affected-fraction inclusion rule -------------
    frac = dmg["b_aff_sf"] / dmg["bdg_sfc"]
    print(f"\n[2] damaged-only: b_aff_sf>0 for {int((dmg['b_aff_sf'] > 0).sum()):,}/{n:,}; "
          f"affected fraction min {frac.min():.3f}, median {frac.median():.3f} (>=0.50 rule)")

    # 3) footprints == our Overture base (id match by adm1 + geometry IoU) ------
    ov = s.az_path("silver", "source=overture", "adm0=VE", "region=*", "part-*.parquet")
    ovids = set(con.execute(f"SELECT DISTINCT id FROM read_parquet('{ov}')").df()["id"].astype(str))
    d4 = dmg.to_crs(4326)
    d4["inov"] = d4["id"].astype(str).isin(ovids)
    print(f"\n[3] id present in our Overture base: {int(d4['inov'].sum()):,}/{n:,} "
          f"({100 * d4['inov'].mean():.0f}%)  [gaps = states we haven't pulled]")
    print("    id-match by adm1 (covered states = 1.0):",
          d4.groupby("adm1_name")["inov"].mean().round(2).sort_values(ascending=False).head(6).to_dict())
    box = (-66.95, 10.55, -66.80, 10.65)  # La Guaira, a covered area
    ovg = con.execute(
        f"SELECT ST_AsWKB(geometry) w FROM read_parquet('{ov}') "
        f"WHERE ST_XMin(geometry) BETWEEN {box[0]} AND {box[2]} "
        f"AND ST_YMin(geometry) BETWEEN {box[1]} AND {box[3]}"
    ).df()
    og = [from_wkb(bytes(b)) for b in ovg["w"]]
    tree = STRtree(og)
    ious = []
    for g in d4.cx[box[0]:box[2], box[1]:box[3]].geometry.values[:1000]:
        best = 0.0
        for k in tree.query(g, predicate="intersects"):
            o = og[k]
            inter = g.intersection(o).area
            if inter > 0:
                best = max(best, inter / (g.area + o.area - inter))
        ious.append(best)
    ious = np.array(ious)
    print(f"    geometry IoU vs Overture (La Guaira, n={len(ious)}): "
          f"median {np.median(ious):.3f}, share >=0.99 {100 * (ious >= 0.99).mean():.0f}%")

    # 4) AOI envelops v1 -------------------------------------------------------
    # NB: reads the CURRENT impact silver analysed_extent — valid only BEFORE
    # harmonize_impact_v2 overwrites it with the v2 AOI (after which this is ~100%
    # trivially). The pre-supersede result is recorded in findings.md.
    ext = s.az_path("silver", "source=impact_initiatives", "adm0=VE", "analysed_extent.parquet")
    old = from_wkb(bytes(con.execute(
        f"SELECT ST_AsWKB(ST_Union_Agg(ST_MakeValid(geometry))) FROM read_parquet('{ext}')"
    ).fetchone()[0]))
    new = aoi.to_crs(4326).geometry.union_all()
    print(f"\n[4] v2 AOI vs v1 analysed_extent: fraction of v1 covered "
          f"{100 * old.intersection(new).area / old.area:.0f}% | new/old area "
          f"{new.area / old.area:.1f}x")


if __name__ == "__main__":
    main()
