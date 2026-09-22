"""Build UNOSAT silver: one GeoParquet per distinct layer content, under event-code partitions.

Reads bronze only. Per flood/cyclone dataset the geometry source is the
geodatabase zip when the dataset has one, otherwise its shapefile zip; when
both exist the shapefile is read only to cross-check layer NAMES against the
geodatabase, and any disagreement is recorded as `shp_gdb_mismatch` on the
dataset's processing rows (no shapefile geometry is read in that case).

Each layer is hashed (`readers.content_hash`) and written to
`unosat/silver/{observed_event,coverage}/code={EventCode}/layer={hash}.parquet`.
The path already existing is the idempotency check: a layer re-shipped
identically across many HDX zips is written once and every later encounter is
recorded `ok` with `reused=True`. `sources` is written per code, and the
processing ledger is checkpointed every 25 layers to {work_dir} and to
unosat/silver/_meta/processing.parquet. Resumable: (sha256, layer) pairs
already in the processing ledger are skipped.

Statuses: ok | unclassified | skipped_non_water | no_date | unreadable. Only a
GDAL failure on a single layer becomes `unreadable` (recorded with its error
text, the run continues); everything else raises.

`sources` is written only for codes this run processed in full, so a partial
run never leaves behind a summary that looks complete and is not; the run
prints the `--force --codes ...` invocation that rebuilds the ones it skipped.

Run:  uv run --group etl --group api python pipelines/unosat/silver.py \
          [--stage dev] [--codes FL20220424SSD,...] [--limit N] [--force]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyogrio
from pyogrio.errors import DataLayerError, DataSourceError

from gie import blobio
from gie.unosat import cache, common, domains, grammar, layers, meta, readers, silver, store

# Checkpoint frequency: persist every N layers so a kill mid-batch loses at
# most this many layers' worth of re-work, never silently drops done work.
CHECKPOINT_EVERY = 25


def domain_lookups(domain_rows: pd.DataFrame, sha256: str) -> dict[str, dict[str, dict[str, str]]]:
    """``{layer: {field: {code: value}}}`` for one geodatabase content.

    The binding is per layer AND field (see `domains.py`): the same GDB binds
    `Water_Class` on its 2014 layers and `Water_Class2` on its 2021 ones.
    """
    sub = domain_rows[domain_rows["sha256"] == sha256]
    out: dict[str, dict[str, dict[str, str]]] = {}
    for (layer, field), grp in sub.groupby(["layer", "field"]):
        out.setdefault(layer, {})[field] = dict(zip(grp["code"], grp["value"], strict=True))
    return out


def shp_member_for(members: list[str], layer: str) -> str | None:
    """The zip member path whose basename is ``layer``.shp, or None."""
    for m in members:
        if m.lower().endswith(".shp") and m.split("/")[-1][:-4] == layer:
            return m
    return None


def gdb_layer_paths(gdbs: list[tuple[str, Path]]) -> dict[str, Path]:
    """``{feature class name: extracted .gdb path}`` across every geodatabase
    in one zip. First writer wins if two geodatabases in the same zip use the
    same layer name — the processing ledger is keyed on (sha256, layer), so
    the pair must resolve to exactly one read."""
    out: dict[str, Path] = {}
    for _, path in gdbs:
        for name in pyogrio.list_layers(path)[:, 0]:
            out.setdefault(name, path)
    return out


def read_layer(source: str, path: Path, layer: str, member: str | None):
    """One layer as a GeoDataFrame. Raises `DataSourceError`/`DataLayerError`
    for a GDAL failure, which the caller records as `unreadable`.

    A shapefile layer with no member path is not a GDAL failure but a
    contradiction — the SHP inventory is built *from* the member list — so it
    raises rather than being recorded as an unreadable layer.
    """
    if source == "gdb":
        return readers.read_gdb_layer(path, layer)
    if member is None:
        raise RuntimeError(
            f"layer {layer!r} is inventoried for {path.name} but no .shp member of that "
            "name is in zip_contents.parquet"
        )
    return readers.read_shp_member(path, member)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--codes", default=None, help="comma-separated event codes to restrict to")
    ap.add_argument("--limit", type=int, default=None, help="max source zips to process")
    ap.add_argument(
        "--force",
        action="store_true",
        help="revisit layers already in the processing ledger (layer files that exist are "
        "still not rewritten); the way to rebuild a code's sources table after a partial run",
    )
    args = ap.parse_args(argv)

    cc = meta.bootstrap(args.work_dir, args.stage)
    blob_store = store.DataLakeStore(blobio.uploader(common.global_settings(args.stage)), cc)

    ledger = pd.read_parquet(args.work_dir / "resources.parquet")
    units = silver.select_units(ledger)
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",")}
        units = [u for u in units if u["code"] in wanted]

    layers_df, _ = layers.load_frames(args.work_dir)
    domain_rows, _ = domains.load_frames(args.work_dir)
    contents = pd.read_parquet(args.work_dir / "zip_contents.parquet")

    proc_df = silver.load_processing(args.work_dir)
    done = set(zip(proc_df["sha256"], proc_df["layer"], strict=True))

    # A unit whose every inventoried layer is already in the processing ledger
    # needs no download at all.
    inventory = {sha: grp for sha, grp in layers_df.groupby("sha256")}

    def pending(unit: dict) -> list:
        inv = inventory.get(unit["sha256"])
        if inv is None:
            return []
        inv = inv.drop_duplicates("layer")
        if args.force:
            return list(inv.itertuples())
        return [r for r in inv.itertuples() if (unit["sha256"], r.layer) not in done]

    # Counted over units that *can* be processed, so a code whose only gap is
    # an uninventoriable zip can still have its sources table written.
    selected_by_code: dict[str, int] = {}
    for u in units:
        if u["sha256"] in inventory:
            selected_by_code[u["code"]] = selected_by_code.get(u["code"], 0) + 1

    # A zip with no inventory rows is not silently absent from silver: it is a
    # recorded state in layers_status.parquet (zip_unreadable, gdb_unreadable,
    # no_layers) and is reported here so it is never mistaken for done work.
    no_inventory = [u for u in units if u["sha256"] not in inventory]
    todo = [u for u in units if u["sha256"] in inventory and pending(u)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"source zips: {len(units)}, to process: {len(todo)}")
    if no_inventory:
        print(
            f"  {len(no_inventory)} have no inventoried layers "
            "(see layers_status.parquet for why); nothing to build for them"
        )

    new_rows: list[dict] = []
    src_rows: dict[str, list[dict]] = {}
    processed_by_code: dict[str, int] = {}

    def checkpoint() -> None:
        nonlocal proc_df, new_rows
        if not new_rows:
            return
        proc_df = silver.merge_processing(proc_df, new_rows)
        proc_df.to_parquet(args.work_dir / silver.PROCESSING_FILE)
        blob_store.upload(
            f"{common.SILVER_META}/processing.parquet",
            (args.work_dir / silver.PROCESSING_FILE).read_bytes(),
        )
        new_rows = []

    def process_layer(unit: dict, inv_row, zip_path: Path, gdb_paths, members, lookups, mismatch):
        """One layer end-to-end. Appends its processing record; writes the
        layer file BEFORE the record exists, so a crash between the two leaves
        the pair looking undone and it is simply redone."""
        layer = inv_row.layer
        ln = grammar.parse(layer)
        common_kw = {
            "sha256": unit["sha256"],
            "layer": layer,
            "code": unit["code"],
            "code_method": unit["code_method"],
            "geometry_source": unit["geometry_source"],
            "target_ids": unit["target_ids"],
            "shp_gdb_mismatch": mismatch,
        }
        prescreened = silver.prescreen(ln, inv_row.geometry_type)
        if prescreened is not None:
            new_rows.append(silver.processing_row(**common_kw, status=prescreened))
            return

        if unit["geometry_source"] == "gdb" and layer not in gdb_paths:
            # ogrinfo inventoried it but GDAL cannot open it through pyogrio now:
            # our side failing on one layer, recorded, run continues.
            new_rows.append(
                silver.processing_row(
                    **common_kw,
                    status="unreadable",
                    error=f"inventoried layer {layer!r} not found in any .gdb in this zip",
                )
            )
            return

        try:
            gdf = read_layer(
                unit["geometry_source"],
                gdb_paths[layer] if unit["geometry_source"] == "gdb" else zip_path,
                layer,
                shp_member_for(members, layer),
            )
        except (DataSourceError, DataLayerError) as e:
            new_rows.append(
                silver.processing_row(
                    **common_kw, status="unreadable", error=f"{type(e).__name__}: {e}"[:500]
                )
            )
            return

        chash = readers.content_hash(gdf)
        path = silver.silver_layer_path(ln.table, unit["code"], chash)
        groups = silver.layer_acquisitions(ln, gdf)
        acqs = [acq for acq, _ in groups]

        def add_sources() -> None:
            """`sources` is accumulated even for a layer whose file is reused,
            so a code's summary describes all of its layers and not only the
            ones this run happened to write."""
            src_rows.setdefault(unit["code"], []).extend(
                silver.source_rows(unit["code"], ln, acqs)
            )

        if blob_store.exists_size(path) is not None:
            # Identical content already in silver under this code: nothing to
            # write. `reused` rows carry no kind counts — the authoritative
            # counts sit on the row that first wrote this content.
            new_rows.append(
                silver.processing_row(
                    **common_kw,
                    status=silver.acq_status(acqs),
                    table=ln.table,
                    content_hash=chash,
                    n_polygons=len(gdf),
                    reused=True,
                )
            )
            add_sources()
            return

        frame, table, record = silver.build_layer(
            unit["code"],
            unit["code_method"],
            ln,
            gdf,
            source=unit["geometry_source"],
            sha256=unit["sha256"],
            target_ids=unit["target_ids"],
            domain_lookup=lookups.get(layer),
            content_hash=chash,
        )
        if frame is not None:
            # File first, ledger second: a crash between the two leaves the
            # (sha256, layer) pair looking undone, so it is simply redone.
            silver.write_layer(blob_store, silver.silver_layer_path(table, unit["code"], chash),
                               frame)
            add_sources()
        new_rows.append(record | {"shp_gdb_mismatch": mismatch})

    try:
        for i, unit in enumerate(todo, 1):
            sha = unit["sha256"]
            inv_rows = pending(unit)
            zip_path = cache.read_through(
                sha,
                unit["resource_name"],
                lambda u=unit: cc.download_blob(
                    common.blob_path(u["sha256"], u["resource_name"])
                ).readall(),
            )
            mismatch: list[str] = []
            if unit["geometry_source"] == "gdb" and unit["sibling_shp_sha256s"]:
                shp_inv = layers_df[layers_df["sha256"].isin(unit["sibling_shp_sha256s"])]
                mismatch = silver.layer_mismatch(
                    set(layers_df.loc[layers_df["sha256"] == sha, "layer"]),
                    set(shp_inv["layer"]),
                )
            lookups = domain_lookups(domain_rows, sha)
            members = contents.loc[contents["sha256"] == sha, "member"].tolist()

            if unit["geometry_source"] == "gdb":
                with readers.extract_gdbs(zip_path) as gdbs:
                    gdb_paths = gdb_layer_paths(gdbs)
                    for inv_row in inv_rows:
                        process_layer(unit, inv_row, zip_path, gdb_paths, members, lookups,
                                      mismatch)
                        if len(new_rows) >= CHECKPOINT_EVERY:
                            checkpoint()
            else:
                for inv_row in inv_rows:
                    process_layer(unit, inv_row, zip_path, {}, members, lookups, mismatch)
                    if len(new_rows) >= CHECKPOINT_EVERY:
                        checkpoint()

            processed_by_code[unit["code"]] = processed_by_code.get(unit["code"], 0) + 1
            print(
                f"  [{i}/{len(todo)}] {unit['code']} {unit['resource_name']} "
                f"({len(inv_rows)} layers, source={unit['geometry_source']})",
                flush=True,
            )
    finally:
        # Persists whatever completed before a Ctrl-C or an exception, so an
        # interrupted run never loses already-processed layers.
        checkpoint()

    # `sources` is a per-code summary of everything that code's layers
    # resolved to, so it is only written for codes this run saw in full.
    # Writing it from a partial (resumed or --limit) run would produce a file
    # that looks complete and is not; a missing file is the visible state, and
    # the rerun that fixes it is printed below.
    written, partial = 0, []
    for code, rows in src_rows.items():
        if processed_by_code.get(code) != selected_by_code[code]:
            partial.append(code)
            continue
        silver.write_layer(blob_store, silver.sources_path(code), silver.sources_frame(rows))
        written += 1
    print(f"sources written for {written} codes")
    if partial:
        print(
            f"  {len(partial)} codes were only partly processed in this run, so their sources "
            "table was NOT written (it would describe only part of the code). Rebuild with:\n"
            f"    --force --codes {','.join(sorted(partial)[:20])}"
            + (" (first 20)" if len(partial) > 20 else "")
        )

    if len(proc_df):
        print(proc_df["status"].value_counts().to_string())
    else:
        print("nothing processed")


if __name__ == "__main__":
    main()
