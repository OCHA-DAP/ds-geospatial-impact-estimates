"""Build UNOSAT gold v2: label sets per (code, area, acquisition interval).

Reads silver only. Per event code it concatenates every layer file of the
`observed_event` and `coverage` partitions — the blob listing decides what a
partition holds, `silver.iter_layer_files` fetches what the local mirror
lacks — dissolves them into label sets (`gie.unosat.gold.build_code`) and
writes two files:

  gold/labels/code={EventCode}/data.parquet   multi-geometry GeoParquet,
      primary geometry `geom_water`, plus `geom_flood`, `geom_possible` and
      the `geom_valid` mask. Rasterise all four in the dataloader; pixels
      outside the mask are unobserved, not dry.
  gold/_index_parts/code={EventCode}.parquet  the geometry-free index rows
      for that code.

At the end of every run the parts are concatenated into
`gold/label_index.parquet` — from the blob listing, not from what this run
happened to build, so a resumed run never publishes an index that covers only
part of the corpus.

**Resumable per code.** A code with both files already in blob is skipped
(`--force` rebuilds it), so a killed run costs only the code it was on. As in
silver, every file is written to the local mirror first and uploaded from
there in the background: a stalled socket never loses built work.

**Fail loud.** One code that cannot be built stops the run. It is cheap to
fix and rerun — everything already built is skipped — and a corpus-wide index
assembled around a code that silently failed is worse than no index.

Run:  uv run --group etl --group api python pipelines/unosat/gold.py \
          [--stage dev] [--codes FL20220424SSD,...] [--limit N] [--force]
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor

import pandas as pd
from azure.core.exceptions import AzureError

from gie import blobio
from gie.unosat import common, gold, meta, silver, store

# Small files, but the same stalling network silver tuned for.
UPLOAD_WORKERS = 6
UPLOAD_READ_TIMEOUT = 60


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--codes", default=None, help="comma-separated event codes to restrict to")
    ap.add_argument("--limit", type=int, default=None, help="max codes to build")
    ap.add_argument(
        "--force", action="store_true", help="rebuild codes whose gold files already exist"
    )
    args = ap.parse_args(argv)

    cc = meta.bootstrap(args.work_dir, args.stage)
    blob_store = store.DataLakeStore(
        blobio.uploader(common.global_settings(args.stage), read_timeout=UPLOAD_READ_TIMEOUT), cc
    )

    ledger_path = args.work_dir / "resources.parquet"
    if not ledger_path.exists():
        raise FileNotFoundError(
            f"{ledger_path} missing — run pipelines/unosat/discovery.py first "
            "(it is restored from unosat/bronze/_meta when present)"
        )
    meta_by_code = gold.code_meta(pd.read_parquet(ledger_path))

    codes = gold.list_silver_codes(blob_store)
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    done = set() if args.force else gold.built_codes(blob_store)
    todo = [c for c in codes if c not in done]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"codes with silver: {len(codes)}, already built: {len(done)}, to build: {len(todo)}")

    upload_pool = ThreadPoolExecutor(max_workers=UPLOAD_WORKERS)
    uploads: dict[Future, str] = {}

    def publish(blob_path: str, frame) -> None:
        """Mirror first, then upload from the file on disk — so an upload that
        stalls or dies never loses what was built."""
        local = gold.local_path(args.work_dir, blob_path)
        silver.write_layer_local(local, frame)
        uploads[upload_pool.submit(silver.upload_file, blob_store, blob_path, local)] = blob_path

    def drain() -> None:
        """Wait out the in-flight uploads, raising on the first failure with
        every failed path named."""
        failed: list[str] = []
        for fut, blob_path in list(uploads.items()):
            try:
                fut.result()
            except (AzureError, OSError) as e:
                failed.append(f"{blob_path}: {type(e).__name__}: {e}")
            uploads.pop(fut)
        if failed:
            raise OSError(f"{len(failed)} gold uploads failed: {failed[:5]}")

    try:
        for i, code in enumerate(todo, 1):
            observed = gold.read_partition(args.work_dir, blob_store, "observed_event", code)
            if not len(observed):
                # A code named on the command line that silver never wrote is a
                # mistake worth stopping for; an empty gold partition would look
                # like a code with no water.
                raise FileNotFoundError(
                    f"{code}: no observed_event layer files in "
                    f"{common.SILVER}/observed_event/code={code}/ — silver has not run for it"
                )
            coverage = gold.read_partition(args.work_dir, blob_store, "coverage", code)
            labels, index = gold.build_code(
                code, observed, coverage, meta_by_code.get(code, {})
            )
            publish(gold.labels_path(code), labels)
            publish(gold.index_part_path(code), index)
            print(
                f"  [{i}/{len(todo)}] {code}: {len(index)} label sets "
                f"from {len(observed)} polygons, {len(coverage)} coverage rows",
                flush=True,
            )
    finally:
        # Persists (and reports on) whatever completed before an exception, so
        # an interrupted run leaves its finished codes uploaded and skippable.
        drain()
        upload_pool.shutdown(wait=True)

    index = gold.concat_index(gold.iter_index_parts(args.work_dir, blob_store))
    local_index = gold.local_path(args.work_dir, gold.INDEX_PATH)
    silver.write_layer_local(local_index, index)
    silver.upload_file(blob_store, gold.INDEX_PATH, local_index)

    print(f"\nlabel_index: {len(index):,} label sets -> {gold.INDEX_PATH}")
    if len(index):
        print(f"  with label_day: {int(index['label_day'].notna().sum()):,}")
        for column in ("sensor_class", "acq_precision", "valid_basis", "valid_match"):
            counts = index[column].value_counts(dropna=False).to_dict()
            print(f"  by {column}: {counts}")
        # Separable and non-empty are different states: a set whose flood layer
        # looked and found none carries an empty geometry of area 0, and would
        # be indistinguishable from a real flood label under one count.
        separable = int(index["flood_area_km2"].notna().sum())
        non_empty = int((index["flood_area_km2"] > 0).sum())
        print(f"  label sets with a separable flood geometry: {separable:,}")
        print(f"  label sets with a non-empty flood geometry: {non_empty:,}")


if __name__ == "__main__":
    main()
