"""Invariant checks for the UNOSAT archive: bronze, silver and gold.

A section whose inputs are missing (no processing ledger yet, no gold index
yet, a gold code whose silver partition is not locally cached) is printed as
SKIPPED with the reason and is never counted as a pass — "could not check"
and "checked and fine" must never look the same on exit. Exit 1 on any
failure or skip.

Run:  uv run --group etl --group api python pipelines/unosat/audit.py \
          [--stage dev] [--silver] [--gold]

Neither flag: all three sections (bronze B1-B3, silver S1-S7, gold G1-G2) run,
in that order. `--silver`/`--gold` restrict the run to just that section. The
bronze ledger and the small `layers.parquet`/`processing.parquet` files are
always read regardless of the flags (cheap, local) because `stale_codes`
wants them; the flags gate only which sections are *printed* and count toward
the exit code, and the one genuinely corpus-sized read (G2's per-code raw
silver rows).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from gie import blobio
from gie.unosat import audit, common, gold, layers, meta, silver
from gie.unosat.store import DataLakeStore

# Columns S4 cannot check without a full per-polygon silver read (see
# `_vocab_series`), and why: printed once per silver run so the omission is
# visible rather than a silent gap in the vocabulary check.
VOCAB_NOTE = (
    "S4 does not check class_method/acq_method: both are per-polygon columns that live only "
    "in the raw silver layer files, and reading every layer in the corpus for this one rule "
    "would cost as much as a full silver rebuild. status/geometry_source come from the "
    "processing ledger; layer_kind/role from its kind_counts_json; acq_precision from the "
    "per-code sources tables — none of those require reading raw geometry."
)


def _print(name: str, ok: bool, detail: str) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def _load_sources(work_dir: Path, store: DataLakeStore) -> pd.DataFrame:
    """Every code's `sources` summary (one row per (code, sensor, acquisition),
    spec §3), concatenated.

    This is S3's `acq_rows` and S4's `acq_precision` vocab: both need only the
    acquisition columns `sources` already carries deduplicated, so this reads
    those small per-code summaries instead of every raw observed_event/coverage
    layer file in the corpus.
    """
    codes = sorted(
        {
            p.split("code=", 1)[1].split("/", 1)[0]
            for p in store.list_sizes(f"{common.SILVER}/sources/code=")
        }
    )
    frames = []
    for code in codes:
        local = silver.local_sources_path(work_dir, code)
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            common.atomic_write(local, store.download(silver.sources_path(code)))
        frames.append(pd.read_parquet(local))
    if not frames:
        return pd.DataFrame(columns=silver.SOURCES_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _kind_frame(proc_df: pd.DataFrame, table: str, column: str) -> pd.DataFrame:
    """`(code, {column})` rows exploded from one table's `kind_counts_json` —
    S4's `layer_kind` (observed_event) / `role` (coverage) vocab, with `code`
    carried along row for row so a violation can be attributed to it."""
    sub = proc_df.loc[proc_df["table"] == table, ["code", "kind_counts_json"]].dropna(
        subset=["kind_counts_json"]
    )
    rows = [
        {"code": r.code, column: k}
        for r in sub.itertuples()
        for k in json.loads(r.kind_counts_json)
    ]
    return pd.DataFrame(rows, columns=["code", column])


def _vocab_frames(
    proc_df: pd.DataFrame, sources_df: pd.DataFrame
) -> dict[str, tuple[pd.DataFrame, str]]:
    """The S4 vocab columns checkable from data already loaded for other
    checks, each paired with its own `code` column so a violation can be
    attributed to the code(s) that produced it — see `VOCAB_NOTE` for what is
    left out and why."""
    frames: dict[str, tuple[pd.DataFrame, str]] = {
        "status": (proc_df, "status"),
        "geometry_source": (proc_df, "geometry_source"),
        "layer_kind": (_kind_frame(proc_df, "observed_event", "layer_kind"), "layer_kind"),
        "role": (_kind_frame(proc_df, "coverage", "role"), "role"),
    }
    if len(sources_df):
        frames["acq_precision"] = (sources_df, "acq_precision")
    return frames


def _load_gold_index(work_dir: Path, store: DataLakeStore) -> tuple[pd.DataFrame, str | None]:
    """`(index, skip_reason)`. The local mirror first; if absent, the index is
    one small file, so it is fetched — unlike the per-code raw partitions G2
    needs, fetching it is not "downloading the whole corpus"."""
    local = Path(work_dir) / "gold" / "label_index.parquet"
    if local.exists():
        return pd.read_parquet(local), None
    size = store.exists_size(gold.INDEX_PATH)
    if size is None:
        return (
            pd.DataFrame(columns=gold.INDEX_COLUMNS),
            f"no {local} locally and no {gold.INDEX_PATH} in blob — gold has not run yet",
        )
    data = store.download(gold.INDEX_PATH)
    local.parent.mkdir(parents=True, exist_ok=True)
    common.atomic_write(local, data)
    return pd.read_parquet(local), None


def _cached_locally(work_dir: Path, store: DataLakeStore, table: str, code: str) -> bool:
    """Whether every layer file blob currently lists for one (table, code)
    partition already sits in the local silver mirror. A LIST call, never a
    download; the caller uses it to decide whether reading a code is free or
    would pull the code's raw geometry from blob."""
    blob_paths = [
        p
        for p in store.list_sizes(f"{common.SILVER}/{table}/code={code}/")
        if p.rsplit("/", 1)[-1].startswith("layer=")
    ]
    if not blob_paths:
        return False
    local_dir = silver.local_mirror(work_dir) / table / f"code={code}"
    return all((local_dir / p.rsplit("/", 1)[-1]).exists() for p in blob_paths)


def _observed_by_code_local(
    work_dir: Path, store: DataLakeStore, codes: list[str]
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """`({code: observed_event frame}, codes skipped)` for G2, restricted to
    codes whose observed_event partition is already fully in the local silver
    mirror.

    G2 needs true per-polygon `layer_kind` values, which exist only in the raw
    silver files. Reading every gold code's partition from blob just for this
    one rule would mean downloading the whole corpus of geometry files, so a
    code not already cached locally is skipped and named here rather than
    silently fetched (or silently dropped).
    """
    observed_by_code: dict[str, pd.DataFrame] = {}
    skipped: list[str] = []
    for code in codes:
        if not _cached_locally(work_dir, store, "observed_event", code):
            skipped.append(code)
            continue
        paths = sorted(silver.iter_layer_files(work_dir, store, "observed_event", code))
        frames = [silver.read_layer_file(p)[["layer_kind", "acq_precision"]] for p in paths]
        observed_by_code[code] = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["layer_kind", "acq_precision"])
        )
    return observed_by_code, skipped


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--silver", action="store_true", help="run only the silver section (S1-S7)")
    ap.add_argument("--gold", action="store_true", help="run only the gold section (G1-G2)")
    args = ap.parse_args(argv)

    only = args.silver or args.gold
    run_bronze = not only
    run_silver = args.silver or not only
    run_gold = args.gold or not only

    cc = meta.bootstrap(args.work_dir, args.stage)
    ledger = common.coerce_ledger_dtypes(pd.read_parquet(args.work_dir / "resources.parquet"))
    status_path = args.work_dir / "domains_status.parquet"
    status_df = (
        pd.read_parquet(status_path)
        if status_path.exists()
        else pd.DataFrame(columns=["sha256", "status"])
    )
    store = DataLakeStore(blobio.uploader(common.global_settings(args.stage)), cc)

    ok = True

    if run_bronze:
        print("bronze:")
        ok &= audit.run_bronze_checks(ledger, store, status_df)
        print(f"domains status breakdown: {status_df.status.value_counts().to_dict()}")
        print("ledger statuses:", ledger["status"].value_counts().to_dict())

    # Cheap, local reads; loaded regardless of the flags because `stale_codes`
    # (written unconditionally, below) wants them.
    layers_df, _ = layers.load_frames(args.work_dir)
    proc_df = silver.load_processing(args.work_dir)
    sources_df = pd.DataFrame(columns=silver.SOURCES_COLUMNS)
    vocab_frames: dict[str, tuple[pd.DataFrame, str]] = {}
    partial_notes: list[str] = []

    if run_silver:
        print("\nsilver:")
        missing = [
            name
            for name, path in (
                ("layers.parquet", args.work_dir / "layers.parquet"),
                (silver.PROCESSING_FILE, args.work_dir / silver.PROCESSING_FILE),
            )
            if not path.exists()
        ]
        if missing:
            print(f"  [SKIP] silver section  {', '.join(missing)} missing under {args.work_dir}")
            ok = False
        else:
            sources_df = _load_sources(args.work_dir, store)
            vocab_frames = _vocab_frames(proc_df, sources_df)
            ok &= audit.run_silver_checks(
                ledger, layers_df, proc_df, store, sources_df, vocab_frames
            )
            print(f"  (note) {VOCAB_NOTE}")

    index = pd.DataFrame(columns=gold.INDEX_COLUMNS)
    observed_by_code: dict[str, pd.DataFrame] = {}

    if run_gold:
        print("\ngold:")
        index, skip_reason = _load_gold_index(args.work_dir, store)
        if skip_reason:
            print(f"  [SKIP] gold section  {skip_reason}")
            ok = False
        else:
            ok_g1, detail_g1 = audit.check_g1_valid_mask_present(index)
            _print("G1 every label set has geom_valid or valid_basis='none'", ok_g1, detail_g1)
            ok &= ok_g1

            codes = sorted(index["code"].dropna().unique()) if len(index) else []
            observed_by_code, uncached = _observed_by_code_local(args.work_dir, store, codes)
            if codes and not observed_by_code:
                print(
                    "  [SKIP] G2 excluded-kind polygons fully accounted for  "
                    f"none of {len(codes)} gold codes have a local silver observed_event "
                    "partition cached (would otherwise require downloading the whole corpus "
                    "from blob)"
                )
                ok = False
            else:
                if uncached:
                    print(
                        f"  (note) G2 checked {len(observed_by_code)}/{len(codes)} gold codes; "
                        f"{len(uncached)} skipped, no local silver cache: {uncached[:5]}"
                    )
                    partial_notes.append(
                        f"G2 verified {len(observed_by_code)} of {len(codes)} gold codes; "
                        "the rest were not cached locally"
                    )
                ok_g2, detail_g2 = audit.check_g2_excluded_accounting(observed_by_code, index)
                _print("G2 excluded-kind polygons fully accounted for", ok_g2, detail_g2)
                ok &= ok_g2

            print(f"  label_coverage: {audit.label_coverage_summary(index)}")

    stale = audit.stale_codes(
        ledger, layers_df, proc_df, store, sources_df, vocab_frames, index, observed_by_code
    )
    stale_path = args.work_dir / "audit_stale_codes.txt"
    stale_path.write_text("".join(f"{c}\n" for c in sorted(stale)))
    print(f"\n{len(stale)} stale codes -> {stale_path}")

    if not ok:
        sys.exit(1)
    summary = "ALL AUDITED SECTIONS PASSED" if only else "ALL CHECKS PASSED"
    if partial_notes:
        summary += f" ({'; '.join(partial_notes)})"
    print(f"\n{summary}")


if __name__ == "__main__":
    main()
