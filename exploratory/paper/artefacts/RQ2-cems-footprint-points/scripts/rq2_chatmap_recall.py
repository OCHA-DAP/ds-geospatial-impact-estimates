"""RQ2e — systematic recall vs ChatMap field-validated damage points (all products).

415 ground-reported damage points (minimal/significant/complete) = miss-side reference.
Per product: restrict to points inside ITS analysed AOI (only accountable where it looked),
ask "is a product-flagged building within r?" — r=20 m PRIMARY (phone GPS error + reporters
stand near, not on, buildings), r=10/50 sensitivity. Grade-stratified. Plus:
  - CEMS row: within the CEMS latest extent, is a CEMS {2,3} point within r of each field
    point? = a field-based CEMS-completeness check (feeds the RQ2/RQ3b attribution debate).
  - Ensemble rows: k-of-4 votes on the Overture base (RQ5 construction).
  - Detected-only sources (hot_osm, disha, unep_debris): NO AOI -> no recall denominator;
    reported separately as raw hit-rates with that caveat.
Flags basis: gold building_flags centroids (uniform across sources; centroid offset is
absorbed by r=20). Figure: field points colored by how many of the 4 AOI products found them.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2_chatmap_recall.py
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
RADII = (20, 10, 50)
GRADES = ("complete", "significant", "minimal")
POS = (2, 3)


def blob_gdf(layer, *parts, columns=None):
    import ocha_stratus as stratus
    b = stratus.load_blob_data(gp.S.blob_path(layer, *parts), stage="dev",
                               container_name=gp.S.container)
    if parts[-1].endswith(".geojson"):
        return gpd.GeoDataFrame.from_features(json.loads(b)["features"], crs=4326)
    df = pd.read_parquet(io.BytesIO(b), columns=columns)
    return df


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


def rate(anchor, targets, r):
    n, d = gp.match_rate(anchor, targets, r)
    return n, d


def main():
    field = blob_gdf("bronze", "source=mapswipe", "adm0=VE", "hdx",
                     "chatmap_field_validated_damage_points.geojson").to_crs(gp.METRIC_CRS)
    print(f"field points: {len(field)}  grades: {field.damaged.value_counts().to_dict()}")

    df = gp.building_flags(columns=["lon", "lat", "ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg",
                                    "list_dmg", "hot_dmg", "disha_dmg",
                                    "debris_dmg"])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    votes = bld[["ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"]].sum(axis=1)
    votes6 = bld[["ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg",
                  "list_dmg", "debris_dmg"]].sum(axis=1)

    cems = gp.to_metric(gp.cems_points())
    cems_pos = cems[cems.damage_class.isin(POS)][["geometry"]]
    ext = gp.cems_extent()
    cems_region = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
            "IMPACT v2": gp.dissolve_union(gp.impact_v2_aoi()),
            "OSU": gp.dissolve_union(gp.osu_aoi()),
            "UH": uh_aoi(),
            "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                  "analysed_extent.parquet"))}
    flags = {"MS": "ms_dmg", "IMPACT v2": "sar_dmg", "OSU": "osu_dmg", "UH": "uh_dmg",
             "LIST": "list_dmg"}
    # core region (rq5b definition): CEMS latest extent ∩ the five product AOIs.
    # UNEP has no AOI; per the frozen source-set decision it is treated as fully
    # covering this core region, so it is scored there rather than getting a
    # detected-only row.
    core = cems_region
    for a in aois.values():
        core = core.intersection(a)

    rows = []
    # -- AOI products + CEMS + ensemble ------------------------------------------
    entries = [(nm, bld[bld[col] == 1], aois[nm]) for nm, col in flags.items()]
    entries.append(("UNEP debris (core region)", bld[bld["debris_dmg"] == 1], core))
    entries.append(("CEMS {2,3}", cems_pos.set_geometry("geometry"), cems_region))
    for k in (1, 2, 3):  # legacy four-member ensemble rows (quad AOI region)
        quad = aois["MS"]
        for a in ("IMPACT v2", "OSU", "UH"):
            quad = quad.intersection(aois[a])
        entries.append((f"≥{k}-of-4 votes", bld[votes >= k], quad))
    for k in (1, 2):  # six-member union/ensemble in the core region
        entries.append((f"≥{k}-of-6 votes (core region)", bld[votes6 >= k], core))
    for nm, flagged, region in entries:
        fin = field[field.geometry.within(region)]
        if len(fin) == 0:
            continue
        row = dict(reference=nm, n_field_in_aoi=len(fin))
        for r in RADII:
            n, d = rate(fin, flagged, r)
            row[f"recall_r{r}"] = round(n / d, 2)
        for gr in GRADES:
            sub = fin[fin.damaged == gr]
            if len(sub) >= 5:
                n, d = rate(sub, flagged, 20)
                row[f"{gr}_r20"] = round(n / d, 2)
                row[f"n_{gr}"] = len(sub)
        rows.append(row)
        print(row)

    # -- detected-only (no AOI -> hit-rate over ALL field points, caveated) -------
    print("\ndetected-only (NO AOI — raw hit-rate over all 415, not comparable recall):")
    for nm, col in (("HOT fAIr", "hot_dmg"), ("DISHA", "disha_dmg")):
        flagged = bld[bld[col] == 1]
        n, d = rate(field, flagged, 20)
        print(f"  {nm:12s}: {n}/{d} = {n/d:.0%} within 20 m")
        rows.append(dict(reference=f"{nm} (detected-only)", n_field_in_aoi=d,
                         recall_r20=round(n / d, 2)))

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2_chatmap_recall.csv"), index=False)
    print("\nwrote rq2_chatmap_recall.csv")

    # -- figure: field points by number of AOI-products that found them (r=20) ----
    found = np.zeros(len(field), dtype=int)
    eligible = np.zeros(len(field), dtype=int)
    for nm, col in flags.items():
        inaoi = field.geometry.within(aois[nm]).to_numpy()
        flagged = bld[bld[col] == 1]
        j = gpd.sjoin_nearest(field[["geometry"]], flagged[["geometry"]],
                              max_distance=20, how="left", distance_col="_d")
        hit = (~j[~j.index.duplicated()]["_d"].isna()).to_numpy()
        found += (hit & inaoi)
        eligible += inaoi
    ll = field.to_crs(4326)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    sc = ax.scatter(ll.geometry.x, ll.geometry.y, c=found, cmap="viridis", s=22,
                    vmin=0, vmax=len(flags))
    ax.scatter(ll.geometry.x[eligible == 0], ll.geometry.y[eligible == 0],
               facecolors="none", edgecolors="red", s=60, lw=0.8,
               label="outside every product AOI")
    plt.colorbar(sc, ax=ax, label=f"# of {len(flags)} AOI products with a flag ≤20 m")
    ax.legend(fontsize=8)
    ax.set_aspect("equal")
    ax.set_title("ChatMap field-validated damage points — who found them? (r=20 m)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq2_chatmap_found_by.png"), dpi=130)
    print("wrote figs/rq2_chatmap_found_by.png")
    print(f"\nfield points outside every product AOI: {(eligible == 0).sum()}")
    print("found-by distribution (eligible pts):",
          dict(pd.Series(found[eligible > 0]).value_counts().sort_index()))


if __name__ == "__main__":
    main()
