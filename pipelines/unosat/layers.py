"""Inventory of every layer inside every archived flood/cyclone zip.

GDB feature classes come from ogrinfo (extracted through domains.extract_gdbs);
SHP members come from the bronze zip inventory (zip_contents.parquet). Writes
{work_dir}/layers.parquet and layers_status.parquet, uploads both to
unosat/silver/_meta/. Resumable: sha256 values already in layers_status are
skipped.

Run:  uv run --group etl --group api python pipelines/unosat/layers.py [--stage dev] [--limit N]
"""

from __future__ import annotations

import argparse
import shutil

import pandas as pd

from gie import blobio
from gie.unosat import cache, common, layers, meta

# Checkpoint frequency: persist every N zips so a kill mid-batch loses at most
# this many zips' worth of re-work, never silently drops already-done work.
CHECKPOINT_EVERY = 25


def shp_members_for(sha256: str, contents: pd.DataFrame) -> list[str]:
    """Distinct member paths recorded for ``sha256`` in the bronze zip
    inventory. A sha256 with no rows at all there (an uploaded resource that
    was never inventoried) is a bronze-stage bug, not a content property —
    the caller does not swallow that into a status."""
    return contents.loc[contents["sha256"] == sha256, "member"].drop_duplicates().tolist()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    if shutil.which("ogrinfo") is None:
        raise RuntimeError("ogrinfo not found on PATH — install GDAL (brew install gdal)")

    cc = meta.bootstrap(args.work_dir, args.stage)

    led = pd.read_parquet(args.work_dir / "resources.parquet")
    zips = led[(led["scope"] == "flood") & led["status"].isin(common.UPLOADED_STATUSES)]
    zips = zips[zips["format"].isin(("Geodatabase", "SHP"))].drop_duplicates("sha256")

    contents = pd.read_parquet(args.work_dir / "zip_contents.parquet")

    # Read once; every checkpoint folds its batch into these frames and writes
    # them, instead of re-reading both parquet files each time.
    rows_df, status_df = layers.load_frames(args.work_dir)
    todo = zips[~zips["sha256"].isin(status_df["sha256"])]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"distinct flood/cyclone zips: {len(zips)}, to process: {len(todo)}")

    all_rows: list[dict] = []
    statuses: list[dict] = []

    def checkpoint() -> None:
        nonlocal rows_df, status_df, all_rows, statuses
        rows_df, status_df = layers.merge_batch(rows_df, status_df, all_rows, statuses)
        layers.persist_frames(args.work_dir, rows_df, status_df)
        all_rows, statuses = [], []

    try:
        for i, r in enumerate(todo.itertuples(), 1):
            path = cache.read_through(
                r.sha256, r.resource_name,
                lambda r=r: cc.download_blob(common.blob_path(r.sha256, r.resource_name)).readall(),
            )
            if r.format == "Geodatabase":
                rows, status, error = layers.layers_for_gdb_zip(r.sha256, r.resource_name, path)
            else:
                if r.sha256 not in contents["sha256"].values:
                    raise RuntimeError(
                        f"{r.sha256} ({r.resource_name}) is uploaded but has no "
                        "zip_contents rows — bronze member inventory is incomplete"
                    )
                members = shp_members_for(r.sha256, contents)
                rows = layers.layers_from_zip_members(r.sha256, r.resource_name, members)
                status, error = ("ok" if rows else "no_layers"), None
            all_rows.extend(rows)
            statuses.append(layers.status_row(r.sha256, status, error))
            print(
                f"  [{i}/{len(todo)}] {r.resource_name} {status} ({len(rows)} layers)", flush=True
            )
            if status in ("gdb_unreadable", "zip_unreadable"):
                print(f"    ** {status}: {error}", flush=True)
            if i % CHECKPOINT_EVERY == 0:
                checkpoint()
    finally:
        # Persists whatever completed before a Ctrl-C or an exception, so
        # interrupted runs never lose already-processed zips.
        if statuses or all_rows:
            checkpoint()

    if len(todo):
        fs = blobio.uploader(common.global_settings(args.stage))
        for name in ("layers.parquet", "layers_status.parquet"):
            blobio.upload(fs, (args.work_dir / name).read_bytes(), f"{common.SILVER_META}/{name}")
    status_path = args.work_dir / "layers_status.parquet"
    if status_path.exists():
        print(pd.read_parquet(status_path)["status"].value_counts().to_string())
    else:
        print("nothing processed")


if __name__ == "__main__":
    main()
