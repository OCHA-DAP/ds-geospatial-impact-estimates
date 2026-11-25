"""RQ1 — CEMS coarse blocks (builtUpA) as ground truth (areal scoring).

CEMS coarse blocks delineate damaged AREAS (the 'early estimate'). They give an areal
negative for free: within the coarse product's analysed extent, a product-damaged building
INSIDE a block = damage-in-damaged-area; OUTSIDE all blocks = false alarm; a block with no
product damage = missed area. We never explode blocks to per-building labels.

Coverage: coarse blocks are monitoring_number==0 (initial) products. Coarse coverage =
union of the initial CEMS analysed-extent polygons, intersected with each product's own AOI.
All metric ops in EPSG:32619.

Metrics per product (within coarse_coverage ∩ product_AOI):
  in_block_rate  = product-damaged buildings inside a block / all product-damaged in region
                   (precision-like vs the coarse damaged-area truth)
  block_recall   = coarse blocks containing >=1 product-damaged building / blocks in region
  grade_concord  = Spearman(block ordinal grade, product-damaged count in block)

Run: uv run --group etl python exploratory/paper/artefacts/RQ1-cems-coarse-blocks/scripts/rq1_coarse_blocks.py
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
M = gp.METRIC_CRS


def load():
    blocks = gp.to_metric(gp.cems_blocks())
    extent = gp.cems_extent()
    print("== CEMS ==")
    print("  blocks:", len(blocks), "| aois:", sorted(blocks.aoi_number.unique().tolist()))
    print("  extent monitoring_number:", extent.monitoring_number.value_counts().to_dict())
    print("  extent aois:", sorted(extent.aoi.unique().tolist()))
    # coarse coverage = initial (monitoring 0) extents, restricted to AOIs that have blocks
    block_aois = set(blocks.aoi_number.unique())
    coarse_ext = extent[(extent.monitoring_number == 0) & (extent.aoi.isin(block_aois))]
    print("  coarse-coverage extent rows:", len(coarse_ext), "| aois:",
          sorted(coarse_ext.aoi.unique().tolist()))
    coarse_cov = gp.to_metric(coarse_ext).geometry.make_valid().union_all()
    # how many blocks fall inside the coarse coverage (sanity)
    inside = blocks[blocks.geometry.representative_point().within(coarse_cov)]
    print(f"  blocks inside coarse coverage: {len(inside)}/{len(blocks)}")
    return blocks, coarse_cov


def product_sets():
    """Return {name: (damaged_points_metric, aoi_union_metric)}."""
    out = {}
    ms = gp.microsoft();      out["Microsoft"] = (gp.points_on_surface(gp.to_metric(ms)),
                                                  gp.dissolve_union(gp.microsoft_aoi()))
    iv2 = gp.impact_v2();     out["IMPACT v2"] = (gp.points_on_surface(gp.to_metric(iv2)),
                                                  gp.dissolve_union(gp.impact_v2_aoi()))
    osu = gp.osu();           out["OSU"] = (gp.points_on_surface(gp.to_metric(osu)),
                                            gp.dissolve_union(gp.osu_aoi()))
    for k, (pts, _) in out.items():
        print(f"  {k}: {len(pts)} damaged buildings")
    return out


def score(name, pts, aoi, blocks, coarse_cov):
    region = coarse_cov.intersection(aoi)
    if region.is_empty:
        print(f"  [{name}] EMPTY region (no overlap of product AOI with coarse coverage)")
        return None
    in_region = pts[pts.within(region)]
    blk = blocks[blocks.intersects(region)].copy()
    # chance baseline: fraction of region AREA covered by blocks. If damage were random,
    # in_block_rate would equal f; lift = in_block_rate / f is the concentration over chance.
    block_area = blk.geometry.intersection(region).area.sum()
    f = block_area / region.area if region.area else float("nan")
    # damaged buildings inside any block
    j = gpd.sjoin(in_region, blk[["geometry", "ems_grade", "damage_class"]],
                  predicate="within", how="left")
    in_block = j["index_right"].notna().sum()
    in_block_rate = in_block / len(in_region) if len(in_region) else float("nan")
    # per-block product-damage count -> block recall + grade concordance
    counts = j.dropna(subset=["index_right"]).groupby("index_right").size()
    blk["n_prod"] = blk.index.map(counts).fillna(0).astype(int)
    block_recall = (blk.n_prod > 0).mean()
    rho, p = spearmanr(blk.damage_class, blk.n_prod) if len(blk) > 2 else (float("nan"), float("nan"))
    lift = in_block_rate / f if f else float("nan")
    print(f"  [{name}] region blocks={len(blk)} dmg_in_region={len(in_region)} "
          f"in_block_rate={in_block_rate:.3f} block_area_frac={f:.3f} lift={lift:.2f} "
          f"block_recall={block_recall:.3f} grade_rho={rho:.3f}(p={p:.3g})")
    return dict(product=name, blocks_in_region=len(blk), dmg_in_region=len(in_region),
                dmg_in_block=int(in_block), in_block_rate=round(in_block_rate, 3),
                block_area_frac=round(f, 3), lift_over_chance=round(lift, 2),
                block_recall=round(block_recall, 3), grade_spearman=round(rho, 3),
                grade_p=round(p, 4))


def main():
    blocks, coarse_cov = load()
    print("== products ==")
    prods = product_sets()
    print("== scoring vs coarse blocks ==")
    rows = [r for name, (pts, aoi) in prods.items()
            if (r := score(name, pts, aoi, blocks, coarse_cov)) is not None]
    df = pd.DataFrame(rows)
    out_csv = os.path.join(os.path.dirname(__file__), "..", "rq1_coarse_summary.csv")
    df.to_csv(out_csv, index=False)
    print("\n", df.to_string(index=False))
    print("wrote", out_csv)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    df.plot.bar(x="product", y=["in_block_rate", "block_recall"], ax=ax[0], rot=0)
    ax[0].set_title("Concordance with CEMS coarse blocks"); ax[0].set_ylim(0, 1)
    ax[0].set_ylabel("rate")
    df.plot.bar(x="product", y="grade_spearman", ax=ax[1], rot=0, color="teal", legend=False)
    ax[1].set_title("Block grade vs product-damage count (Spearman ρ)"); ax[1].set_ylim(-0.2, 1)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq1_coarse_concordance.png"), dpi=130)
    print("wrote figs/rq1_coarse_concordance.png")


if __name__ == "__main__":
    main()
