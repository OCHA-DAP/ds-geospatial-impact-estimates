"""Silver: harmonise the UH building-damage predictions (bronze) -> common schema.

Reads the delivered GeoJSON from bronze and writes ``footprints.parquet`` — every
predicted footprint with its ``grade`` (intact/damaged/destroyed), ``cls`` (1/2/3),
and ``aoi``. This single file feeds both the native tiles (styled by grade) and the
damage projection in harmonize_common, which flags a base building when it CONTAINS
a damaged/destroyed UH footprint's point-on-surface (the impact_v2 id-less-footprint
rule, ADR-0015 — UH footprints ARE ~Overture geometry but carry no id).

Silver is footprints ONLY — there is no analysed-extent parquet. UH grades every
footprint, so the analysed set is derived in harmonize_common straight from the
classifications (the base buildings UH classified, by containment), needing no AOI
polygon (ADR-0018). The provider ships no AOI mask, and every polygon we tried to
DERIVE from the footprints was fragmented (buffered union) or overstated/overlapping
(hulls); if the provider later supplies real AOIs they would only refine coverage —
the damage fraction (damaged / classified) barely moves.

Run: uv run --group etl python pipelines/harmonize_uh.py
"""

from __future__ import annotations

import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import blob, events, ledger
from gie.config import load_settings

SOURCE = "uh"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
DELIVERY_NAME = "final_maxsev_512.geojson"


def _read_bronze(settings) -> gpd.GeoDataFrame:
    bp = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", DELIVERY_NAME, event=EVENT)
    data = stratus.load_blob_data(bp, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".geojson") as tf:
        tf.write(data)
        tf.flush()
        return gpd.read_file(tf.name).to_crs(4326)


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    gdf = _read_bronze(settings)
    print(f"  read {len(gdf):,} footprints from bronze", flush=True)

    # footprints: keep the common-schema columns (grade drives styling + the damage
    # filter; cls is the numeric class 2/3 carried through as the damage grade).
    foot = gdf[["grade", "cls", "aoi", "geometry"]].copy()
    # The delivered GeoJSON has ~13% EXACT-duplicate footprints (61k rows), and 5,644 of
    # those carry CONFLICTING grades — the same building tagged intact AND damaged — which
    # stack in the native view and render as brown blends (grey intact over orange damaged).
    # Collapse exact-geometry duplicates, worst grade winning (destroyed>damaged>intact = max cls).
    n0 = len(foot)
    foot["_wkb"] = foot.geometry.to_wkb()
    foot = (
        foot.sort_values("cls", ascending=False)
        .drop_duplicates("_wkb", keep="first")
        .drop(columns="_wkb")
        .reset_index(drop=True)
    )
    print(f"  deduped {n0:,} -> {len(foot):,} footprints (exact-geometry, worst grade wins)", flush=True)
    foot["adm0"] = ADM0
    foot["source"] = SOURCE
    fblob = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet", event=EVENT
    )
    blob.upload_parquet_staged(foot, fblob, settings)
    n_dmg = int((foot["grade"] != "intact").sum())
    print(f"  silver <- {fblob} ({len(foot):,} footprints, {n_dmg:,} damaged/destroyed)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "UH damage predictions harmonised to silver (graded footprints, detected-only)",
        fblob,
        f"{len(foot):,} deduped footprints ({n_dmg:,} damaged/destroyed), grade intact/"
        f"damaged/destroyed, EPSG:4326; exact-duplicate footprints collapsed worst-grade-wins; "
        f"analysed set derived from classifications in harmonize_common, no AOI polygon (ADR-0018)",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
