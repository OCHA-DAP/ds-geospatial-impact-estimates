"""Silver: harmonise the Microsoft Colombia HDX deliveries onto the common schema.

Companion to ingest_microsoft_hdx.py (Colombia earthquake). Deliveries:

  * pereira          — Vantor 2026-08-12 (Overture + Google bases)
  * cali             — Airbus 2026-08-10 (Overture + Google bases)
  * pereira_extended — Vantor 2026-08-13, HUMAN-REVIEWED (Overture + Google +
                       Microsoft bases). 3.3x the original Pereira mask but NOT
                       a superset: the original's western strip is outside it.

We harmonize the OVERTURE-base gpkg of each delivery (the Google/Microsoft
bases stay bronze-only, for evaluation). The original deliveries carry the
Overture GERS id; the extended delivery's `id` is a plain row index, so it is
nulled here and the common model maps those rows to the base spatially
(point-on-surface, the ADR-0015 rule).

Supersession (per building, not per AOI): the extended run is newer imagery
with human review (367 false alarms rejected), so where it looked it wins —
original pereira rows whose footprint lies inside the extended mask are marked
``superseded``. Outside that mask (the west strip: 6,214 buildings, 9 damaged)
the original stays the active source. Nothing is deleted; silver keeps every
row with the flag, and the serving/native tiers expose only active rows.

Cloud cover: per-building `unknown_pct` (1 = fully obscured), carried through;
the common model treats any unknown_pct > 0 as not-analysed (one rule across
deliveries — NB Microsoft's own HDX summaries exclude only fully-obscured
buildings for the extended run). `review_status` is carried where present.

Run: uv run --group etl python pipelines/harmonize_microsoft_hdx.py
"""

from __future__ import annotations

import fnmatch
import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import blob, events, ledger
from gie.config import load_settings, source_segments

SOURCE = "microsoft"
ADM0 = "CO"  # column value only — CO paths carry no adm0 segment (ADR-0027)
STAGE = "dev"
EVENT = "20260810-co-earthquake"  # validated against events.yaml in main()
AOIS = ("pereira", "cali", "pereira_extended")
# AOIs whose Overture-base ids are NOT GERS (plain row indexes) — nulled in silver.
NO_GERS_ID = {"pereira_extended"}
# newer delivery -> older delivery it supersedes WITHIN its valid-area mask.
SUPERSEDES = {"pereira_extended": "pereira"}
FOOTPRINTS_GLOB = "*overture*.gpkg"
MASK_GLOB = "*valid_area_mask*.geojson"


def _bronze_file(settings, listing: list[str], aoi: str, pattern: str) -> str:
    """The single bronze blob under aoi=<aoi>/ matching pattern — else raise."""
    prefix = settings.blob_path("bronze", f"source={SOURCE}", f"aoi={aoi}", event=EVENT)
    hits = [b for b in listing if b.startswith(prefix + "/")
            and fnmatch.fnmatch(b.rsplit("/", 1)[-1], pattern)]
    if len(hits) != 1:
        raise RuntimeError(
            f"expected exactly one {pattern!r} in bronze for aoi={aoi}, found {hits} — "
            "a new delivery needs a deliberate supersession decision."
        )
    return hits[0]


def _read(settings, blob_name: str) -> gpd.GeoDataFrame:
    data = stratus.load_blob_data(blob_name, stage=STAGE, container_name=settings.container)
    suffix = os.path.splitext(blob_name)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    gdf = gpd.read_file(tmp)
    os.unlink(tmp)
    return gdf


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    listing = list(
        stratus.list_container_blobs(
            name_starts_with=settings.blob_path("bronze", f"source={SOURCE}", event=EVENT),
            stage=STAGE,
            container_name=settings.container,
        )
    )

    foot_parts, mask_parts, src_files = {}, {}, []
    for aoi in AOIS:
        fp_blob = _bronze_file(settings, listing, aoi, FOOTPRINTS_GLOB)
        mk_blob = _bronze_file(settings, listing, aoi, MASK_GLOB)
        src_files += [fp_blob.rsplit("/", 1)[-1], mk_blob.rsplit("/", 1)[-1]]

        fp = _read(settings, fp_blob).to_crs(4326)
        keep = fp[["id", "damaged", "damage_pct_10m", "unknown_pct", "geometry"]].copy()
        # review_status only exists on the reviewed (extended) delivery
        keep["review_status"] = (
            fp["review_status"] if "review_status" in fp.columns else None
        )
        if aoi in NO_GERS_ID:
            keep["id"] = None  # plain row index, NOT an Overture GERS id — never join it
        keep["id"] = keep["id"].astype("string")
        keep["damaged"] = keep["damaged"].astype("int64")
        keep["aoi"] = aoi
        foot_parts[aoi] = keep

        mask = _read(settings, mk_blob).to_crs(4326)
        mask_parts[aoi] = mask[["geometry"]].assign(aoi=aoi)
        print(
            f"  {aoi}: {len(keep):,} buildings ({int(keep['damaged'].sum()):,} damaged), "
            f"{int((keep['unknown_pct'] > 0).sum()):,} cloud-affected; "
            f"mask {len(mask)} polygon(s)",
            flush=True,
        )

    # Per-building supersession: an older delivery's rows inside the newer
    # delivery's mask defer to the newer (reviewed) verdicts; outside it they
    # remain the active source. Silver keeps every row, flagged.
    for aoi_frame in foot_parts.values():
        aoi_frame["superseded"] = False
    for newer, older in SUPERSEDES.items():
        newer_mask = mask_parts[newer].union_all()
        old_frame = foot_parts[older]
        inside = old_frame.geometry.representative_point().within(newer_mask)
        old_frame.loc[inside, "superseded"] = True
        print(
            f"  supersession: {int(inside.sum()):,} of {len(old_frame):,} {older} rows "
            f"inside the {newer} mask -> superseded ({int((~inside).sum()):,} stay active)",
            flush=True,
        )

    foot = gpd.GeoDataFrame(
        pd.concat(foot_parts.values(), ignore_index=True), crs="EPSG:4326"
    )
    foot["adm0"] = ADM0
    foot["source"] = SOURCE
    fblob = settings.blob_path(
        "silver", *source_segments(SOURCE, EVENT), "footprints.parquet", event=EVENT
    )
    blob.upload_parquet_staged(foot, fblob, settings)
    active = foot[~foot["superseded"]]
    n_dmg = int(active["damaged"].sum())
    n_cloud = int((active["unknown_pct"] > 0).sum())
    print(
        f"silver <- {fblob} ({len(foot):,} rows; active {len(active):,}, "
        f"{n_dmg:,} damaged)",
        flush=True,
    )

    ext = gpd.GeoDataFrame(pd.concat(mask_parts.values(), ignore_index=True), crs="EPSG:4326")
    ext["superseded"] = False  # masks all stay valid analysed area (union dedups overlap)
    ext["adm0"] = ADM0
    ext["source"] = SOURCE
    eblob = settings.blob_path(
        "silver", *source_segments(SOURCE, EVENT), "analysed_extent.parquet", event=EVENT
    )
    blob.upload_parquet_staged(ext, eblob, settings)
    print(f"silver <- {eblob} ({len(ext)} valid-area polygons)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "Microsoft CO HDX deliveries harmonised to silver (Overture base)",
        fblob,
        f"{len(foot):,} rows across {', '.join(AOIS)} ({len(active):,} active after "
        f"per-building supersession: pereira defers to the reviewed pereira_extended "
        f"inside its mask); {n_dmg:,} damaged, {n_cloud:,} cloud-affected among active; "
        f"pereira_extended ids nulled (row indexes, not GERS -> spatial join downstream); "
        f"from {', '.join(src_files)}",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
