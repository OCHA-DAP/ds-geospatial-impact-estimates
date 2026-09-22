"""Build UNOSAT silver: one GeoParquet per distinct layer content, under event-code partitions.

Reads bronze only. Per flood/cyclone dataset the geometry source is the
geodatabase zip when the dataset has one, otherwise its shapefile zip — decided
by the LAYER INVENTORY, not by HDX's `format` label, which is wrong for some
resources (`format_label` / `format_mismatch` record the disagreement). When
both exist the shapefile is read only to cross-check layer NAMES against the
geodatabase; any disagreement is `shp_gdb_mismatch` on the dataset's processing
rows, and `sibling_status` says when that check could not be made at all.

Each layer is hashed (`readers.content_hash`) and written to
`{work_dir}/silver/{table}/code={EventCode}/layer={hash}-{name8}.parquet`, then
uploaded in the background to the same relative path under `unosat/silver/`.
`name8` is a short digest of the layer name — two differently-named layers with
identical geometry are two layers, not one. The file already existing (locally
or in blob) is the idempotency check: a layer re-shipped identically across
many HDX zips is written once and every later encounter is recorded `ok` with
`reused=True`.

**The local mirror is disposable; blob is the truth.** It exists so that
building (CPU) and uploading (a network that stalls) do not block each other,
and so a killed run resumes by pushing what it already built: rows with
`uploaded=False` name files that exist locally and need no re-read. Delete
`{work_dir}/silver/` whenever you like — gold refetches from blob through
`silver.iter_layer_files`.

Zips are processed in parallel (`--workers`, default 3) by `silver.process_unit`
in worker processes; the main thread owns the ledger, the uploads and the
printing. `--workers 1` runs them in-process, which is the mode the tests use.

`sources` is written only for codes this run processed in full, so a partial
run never leaves behind a summary that looks complete and is not; the run
prints the `--force --codes ...` invocation that rebuilds the ones it skipped.

Statuses: ok | unclassified | skipped_non_water | no_date | unreadable. Only a
GDAL failure on a single layer becomes `unreadable` (recorded with its error
text, the run continues); an upload failure is recorded on the row as
`uploaded=False` with the error; everything else raises.

Run:  uv run --group etl --group api python pipelines/unosat/silver.py \
          [--stage dev] [--codes FL20220424SSD,...] [--limit N] [--workers 3] [--force]
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures import wait as wait_futures

import pandas as pd
from azure.core.exceptions import AzureError

from gie import blobio
from gie.unosat import cache, common, domains, layers, meta, silver, store

# Checkpoint frequency: persist every N layers so a kill mid-batch loses at
# most this many layers' worth of re-work, never silently drops done work.
CHECKPOINT_EVERY = 25
# Concurrent uploads. Each is a small file (tens of KB); the win is that one
# stalled socket no longer halts the pipeline.
UPLOAD_WORKERS = 6
# Socket timeout for those uploads. The bronze default (300 s) is right for one
# big sequential transfer; here the median upload is 0.5 s and a stall is worth
# abandoning for a fresh connection long before five minutes.
UPLOAD_READ_TIMEOUT = 60


def _upload_error(e: Exception) -> str:
    return f"upload failed: {type(e).__name__}: {e}"[:500]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--codes", default=None, help="comma-separated event codes to restrict to")
    ap.add_argument("--limit", type=int, default=None, help="max source zips to process")
    ap.add_argument(
        "--workers", type=int, default=3, help="zips processed in parallel (1 = in-process)"
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="revisit layers already in the processing ledger (layer files that exist are "
        "still not rewritten); the way to rebuild a code's sources table after a partial run",
    )
    args = ap.parse_args(argv)

    cc = meta.bootstrap(args.work_dir, args.stage)
    blob_store = store.DataLakeStore(
        blobio.uploader(common.global_settings(args.stage), read_timeout=UPLOAD_READ_TIMEOUT), cc
    )

    # An absent inventory is our failure to run a prerequisite, not "nothing to
    # do": without this the run would report zero layers and exit 0. It is also
    # what decides whether each zip is a geodatabase or a shapefile, so it is
    # loaded before the units are selected.
    if not (args.work_dir / "layers.parquet").exists():
        raise FileNotFoundError(
            "layers.parquet missing — run pipelines/unosat/layers.py first "
            "(it is restored from unosat/silver/_meta when present)"
        )
    layers_df, status_df = layers.load_frames(args.work_dir)
    domain_rows, _ = domains.load_frames(args.work_dir)
    contents = pd.read_parquet(args.work_dir / "zip_contents.parquet")

    ledger = pd.read_parquet(args.work_dir / "resources.parquet")
    units = silver.select_units(ledger, layers_df)
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",")}
        units = [u for u in units if u["code"] in wanted]

    proc_df = silver.load_processing(args.work_dir)
    done = set(zip(proc_df["sha256"], proc_df["layer"], strict=True))
    inventory = {sha: grp for sha, grp in layers_df.groupby("sha256")}

    def pending_layers(unit: dict) -> list[dict]:
        """The inventory rows of one zip still to do, as plain dicts — the
        worker runs in another process, so nothing pandas-specific crosses."""
        inv = inventory.get(unit["sha256"])
        if inv is None:
            return []
        inv = inv.drop_duplicates("layer")
        if not args.force:
            inv = inv[~inv["layer"].isin({lyr for sha, lyr in done if sha == unit["sha256"]})]
        return inv[["layer", "geometry_type", "source"]].to_dict("records")

    listed_partitions: dict[tuple[str, str], set[str]] = {}

    def partition_keys(table: str, code: str) -> set[str]:
        """The layer files already in one silver partition, listed once per
        (table, code) and cached. One LIST beats one HEAD per layer: a code with
        300 layers across 35 re-shipped zips would otherwise cost thousands of
        round trips to learn what one listing says."""
        key = (table, code)
        if key not in listed_partitions:
            listed_partitions[key] = set(
                blob_store.list_sizes(f"{common.SILVER}/{table}/code={code}/")
            )
        return listed_partitions[key]

    # ---- uploads ---------------------------------------------------------
    upload_pool = ThreadPoolExecutor(max_workers=UPLOAD_WORKERS)
    uploads: dict[str, Future] = {}  # blob path -> in-flight upload
    waiters: dict[str, list[tuple[str, str]]] = {}  # blob path -> ledger rows awaiting it
    row_index: dict[tuple[str, str], dict] = {}
    new_rows: list[dict] = []

    def enqueue(file_rec: dict) -> None:
        """Queue one mirror file for upload. Two rows can name the same file
        (one layer re-shipped in two zips this run); it is uploaded once and
        every waiting row is flipped when it lands."""
        blob_path = file_rec["blob_path"]
        waiters.setdefault(blob_path, []).append((file_rec["sha256"], file_rec["layer"]))
        if blob_path not in uploads:
            uploads[blob_path] = upload_pool.submit(
                silver.upload_file, blob_store, blob_path, file_rec["local_path"]
            )

    def drain_uploads() -> None:
        """Wait out every in-flight upload and record what happened. Called
        before each checkpoint, so the persisted ledger never claims
        `uploaded=True` for a file still in the air, and a killed run leaves
        `uploaded=False` rows whose local files are already built."""
        for blob_path, fut in list(uploads.items()):
            error = None
            try:
                fut.result()
            except (AzureError, OSError) as e:
                error = _upload_error(e)
            for key in waiters.pop(blob_path, []):
                row = row_index.get(key)
                if row is None:
                    continue
                row["uploaded"] = error is None
                if error:
                    row["error"] = error
            uploads.pop(blob_path)

    def checkpoint() -> None:
        nonlocal proc_df
        drain_uploads()
        if not new_rows:
            return
        # Coerced before writing so the persisted schema is stable run to run
        # and the next run can assign flags into it.
        proc_df = silver.coerce_processing_dtypes(silver.merge_processing(proc_df, new_rows))
        proc_df.to_parquet(args.work_dir / silver.PROCESSING_FILE)
        blob_store.upload(
            f"{common.SILVER_META}/processing.parquet",
            (args.work_dir / silver.PROCESSING_FILE).read_bytes(),
        )
        new_rows.clear()
        row_index.clear()

    def reconcile_uploads() -> None:
        """Push, or account for, everything a previous run built but could not
        show had reached blob. Three outcomes, kept apart: already in blob (the
        row was simply never flipped), present in the mirror (upload it now), or
        nowhere at all (reported, never quietly marked done)."""
        nonlocal proc_df
        stale = silver.unuploaded(proc_df)
        if stale.empty:
            return
        futures: dict[Future, int] = {}
        landed, absent, missing = [], [], []
        for idx, r in stale.iterrows():
            key = silver.layer_file_key(r["content_hash"], r["layer"])
            blob_path = silver.silver_layer_path(
                r["table"], r["code"], r["content_hash"], r["layer"]
            )
            local = silver.local_layer_path(args.work_dir, r["table"], r["code"], key)
            if blob_path in partition_keys(r["table"], r["code"]):
                landed.append(idx)
            elif local.exists():
                fut = upload_pool.submit(silver.upload_file, blob_store, blob_path, local)
                futures[fut] = idx
            else:
                absent.append(idx)
                missing.append(f"{r['sha256'][:8]}/{r['layer']}")
        for fut, idx in futures.items():
            try:
                fut.result()
                landed.append(idx)
            except (AzureError, OSError) as e:
                proc_df.loc[idx, "error"] = _upload_error(e)
                absent.append(idx)
        if landed:
            proc_df.loc[landed, "uploaded"] = True
        if absent:
            # Checked and not there: a definite False, not the null it arrived
            # as. "Unknown" and "known missing" are different states, and only
            # the second is actionable.
            proc_df.loc[absent, "uploaded"] = False
        if landed or absent:
            proc_df.to_parquet(args.work_dir / silver.PROCESSING_FILE)
        print(
            f"resume: {len(stale)} rows had no confirmed upload — "
            f"{len(landed)} confirmed or pushed, {len(missing)} have no file anywhere"
        )
        if missing:
            print(
                "  ** these ledger rows name a layer file that is neither in the mirror nor "
                f"in blob; rebuild them with --force --codes ...: {missing[:5]}"
            )

    # ---- what to do ------------------------------------------------------
    # A zip with no inventory rows is not silently absent from silver: it is a
    # recorded state in layers_status.parquet (zip_unreadable, gdb_unreadable,
    # no_layers) and is reported here so it is never mistaken for done work.
    no_inventory = [u for u in units if u["sha256"] not in inventory]
    todo = [u for u in units if u["sha256"] in inventory and pending_layers(u)]
    if args.limit:
        todo = todo[: args.limit]
    # Counted over units that *can* be processed, so a code whose only gap is
    # an uninventoriable zip can still have its sources table written.
    selected_by_code: dict[str, int] = {}
    for u in units:
        if u["sha256"] in inventory:
            selected_by_code[u["code"]] = selected_by_code.get(u["code"], 0) + 1

    print(f"source zips: {len(units)}, to process: {len(todo)}, workers: {args.workers}")
    if no_inventory:
        print(
            f"  {len(no_inventory)} have no inventoried layers "
            "(see layers_status.parquet for why); nothing to build for them"
        )
    reconcile_uploads()

    src_rows: dict[str, list[dict]] = {}
    processed_by_code: dict[str, int] = {}

    def job_for(unit: dict) -> dict:
        """Everything the worker needs, all picklable. The zip is fetched here,
        on the main thread, because the worker never touches blob."""
        sha = unit["sha256"]
        zip_path = cache.read_through(
            sha,
            unit["resource_name"],
            lambda: cc.download_blob(common.blob_path(sha, unit["resource_name"])).readall(),
        )
        mismatch, sibling_status = silver.sibling_check(
            layers_df, status_df, sha, unit["sibling_shp_sha256s"]
        )
        return {
            "unit": unit,
            "inv_rows": pending_layers(unit),
            "zip_path": zip_path,
            "work_dir": args.work_dir,
            "lookups": silver.domain_lookups(domain_rows, sha),
            "unit_fields": {
                "shp_gdb_mismatch": mismatch,
                "sibling_status": sibling_status,
                "format_label": unit["format_label"],
                "format_mismatch": unit["format_mismatch"],
            },
            "members": contents.loc[contents["sha256"] == sha, "member"].tolist(),
            "known": partition_keys("observed_event", unit["code"])
            | partition_keys("coverage", unit["code"]),
        }

    def apply_result(unit: dict, result: tuple, i: int) -> None:
        rows, files, sources = result
        for row in rows:
            new_rows.append(row)
            row_index[(row["sha256"], row["layer"])] = row
        for file_rec in files:
            enqueue(file_rec)
        for s in sources:
            src_rows.setdefault(s["code"], []).append(s)
        processed_by_code[unit["code"]] = processed_by_code.get(unit["code"], 0) + 1
        print(
            f"  [{i}/{len(todo)}] {unit['code']} {unit['resource_name']} "
            f"({len(rows)} layers, {len(files)} files, source={unit['geometry_source']})",
            flush=True,
        )
        if len(new_rows) >= CHECKPOINT_EVERY:
            checkpoint()

    # ---- run -------------------------------------------------------------
    try:
        if args.workers <= 1:
            for i, unit in enumerate(todo, 1):
                apply_result(unit, silver.process_unit(**job_for(unit)), i)
        else:
            # At most two units per worker are in flight, so the parent's memory
            # and the local cache stay bounded however long the run is.
            pool = ProcessPoolExecutor(max_workers=args.workers)
            in_flight: dict[Future, dict] = {}
            counter = 0

            def collect() -> None:
                nonlocal counter
                finished, _ = wait_futures(in_flight, return_when=FIRST_COMPLETED)
                for fut in finished:
                    counter += 1
                    apply_result(in_flight.pop(fut), fut.result(), counter)

            try:
                for unit in todo:
                    while len(in_flight) >= args.workers * 2:
                        collect()
                    in_flight[pool.submit(silver.process_unit, **job_for(unit))] = unit
                while in_flight:
                    collect()
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
    finally:
        # Persists whatever completed before a Ctrl-C or an exception, so an
        # interrupted run never loses already-processed layers. The checkpoint
        # drains the upload pool first, so shutting it down here cannot strand
        # an upload whose row was already written.
        checkpoint()
        upload_pool.shutdown(wait=True)

    # `sources` is a per-code summary of everything that code's layers resolved
    # to, so it is only written for codes this run saw in full. Writing it from
    # a partial (resumed or --limit) run would produce a file that looks
    # complete and is not; a missing file is the visible state, and the rerun
    # that fixes it is printed below.
    written, partial = 0, []
    for code, rows in src_rows.items():
        if processed_by_code.get(code) != selected_by_code[code]:
            partial.append(code)
            continue
        local = silver.local_sources_path(args.work_dir, code)
        silver.write_layer_local(local, silver.sources_frame(rows))
        silver.upload_file(blob_store, silver.sources_path(code), local)
        written += 1
    print(f"sources written for {written} codes")
    if partial:
        print(
            f"  {len(partial)} codes were only partly processed in this run, so their sources "
            "table was NOT written (it would describe only part of the code). Rebuild with:\n"
            f"    --stage {args.stage} --work-dir {args.work_dir} --force "
            f"--codes {','.join(sorted(partial)[:20])}"
            + (" (first 20)" if len(partial) > 20 else "")
        )

    if len(proc_df):
        print(proc_df["status"].value_counts().to_string())
        print(f"rows with no confirmed upload: {len(silver.unuploaded(proc_df))}")
    else:
        print("nothing processed")


if __name__ == "__main__":
    main()
