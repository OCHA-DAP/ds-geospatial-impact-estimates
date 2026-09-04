"""Transfer every pending target from the discovery ledger into blob:
download -> integrity-check -> inventory members -> upload -> verify -> record.

Resume model (mirrors ADR-0005's blob-existence idempotency):
  - The blob store is the source of truth: before working, the ledger is
    reconciled against a listing of the bronze prefix. Already-uploaded
    targets are skipped; ledger rows claiming "uploaded" whose blob is gone
    are demoted back to pending (loudly).
  - The ledger + journal checkpoint locally AND to blob every N items and on
    exit (including Ctrl-C), so a killed run loses at most the in-flight file.
  - ``--retry-failed`` re-attempts recorded download/upload failures;
    otherwise failures stay visible in the ledger and are not retried.

Everything written to blob (container ``global``):
  copernicus_ems/flood/bronze/code=EMSRnnn/{original basename}.zip
  copernicus_ems/flood/bronze/_meta/{activations,products,zip_contents}.parquet
  copernicus_ems/flood/bronze/_meta/transfers.jsonl   (append-only journal)

Run:  uv run --group etl --group api python pipelines/cems_flood/harvest.py [--limit N]
      [--stage dev] [--retry-failed] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import common
import ocha_stratus as stratus
import pandas as pd

from gie import blobio

CHECKPOINT_EVERY = 25
META_FILES = ("activations.parquet", "products.parquet", "zip_contents.parquet")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def reconcile_with_blob(ledger: pd.DataFrame, stage: str) -> pd.DataFrame:
    """Blob listing is truth: sync ledger statuses to what actually exists.

    Compares SIZES, not just names: a kill mid-upload can leave a created but
    empty/partial DFS file, and a row that already carries a sha256 from a
    failed attempt would otherwise be laundered to uploaded without any check.
    """
    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=stage)
    blob_sizes = {b.name: b.size for b in cc.list_blobs(name_starts_with=f"{common.BRONZE}/code=")}
    got = ledger["blob_path"].map(blob_sizes.get)  # NaN when blob absent
    in_blob = got.notna()
    # sizes agree when the ledger has none recorded yet (backfill fills it) or they match
    size_ok = ledger["size_bytes"].isna() | (got == ledger["size_bytes"])

    to_mark = in_blob & size_ok & (ledger["status"] != "uploaded")
    if to_mark.any():
        print(f"reconcile: {to_mark.sum()} targets already in blob -> uploaded")
        ledger.loc[to_mark, "status"] = "uploaded"
        ledger.loc[to_mark, "error"] = "reconciled: found in blob"

    stale = in_blob & ~size_ok
    if stale.any():
        for tid, ls, bs in zip(
            ledger.loc[stale, "target_id"],
            ledger.loc[stale, "size_bytes"],
            got[stale],
            strict=True,
        ):
            print(
                f"WARNING reconcile: {tid} blob size {int(bs)} != ledger {int(ls)} "
                f"(partial upload?) -> pending re-transfer"
            )
        ledger.loc[stale, "status"] = "pending"

    lost = (ledger["status"] == "uploaded") & ~in_blob & ledger["blob_path"].notna()
    if lost.any():
        print(
            f"WARNING reconcile: {lost.sum()} ledger rows say uploaded but blob is "
            f"MISSING -> demoted to pending: {ledger.loc[lost, 'target_id'].tolist()}"
        )
        ledger.loc[lost, "status"] = "pending"
    return ledger


def journal(work: Path, record: dict) -> None:
    with (work / "transfers.jsonl").open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def transfer_record(row: pd.Series, stage: str, outcome: str, **extra) -> dict:
    """Attempt record; field names follow this repo's data_transfers.jsonl."""
    return {
        "ts": _now(),
        "outcome": outcome,
        "target_id": row["target_id"],
        "source": "copernicus_ems",
        "category": "reference",
        "dataset": f"Copernicus EMS {row['code']} {row['product_class']} product",
        "provider": common.PROVIDER,
        "licence": common.LICENCE,
        "origin_url": row["url"],
        "blob_path": row["blob_path"],
        "stage": stage,
    } | extra


def checkpoint(work: Path, ledger: pd.DataFrame, members: list[dict], fs) -> list[dict]:
    """Persist ledger + member inventory + journal, locally and to blob."""
    ledger.to_parquet(work / "products.parquet")
    contents_path = work / "zip_contents.parquet"
    if members:
        new = pd.DataFrame(members)
        if contents_path.exists():
            old = pd.read_parquet(contents_path)
            old = old[~old["target_id"].isin(new["target_id"].unique())]
            new = pd.concat([old, new], ignore_index=True)
        new.to_parquet(contents_path)
    for name in META_FILES + ("transfers.jsonl",):
        p = work / name
        if p.exists():
            blobio.upload(fs, p.read_bytes(), f"{common.META}/{name}")
    return []  # members are flushed


_thread_local = threading.local()


def _session():
    """One requests.Session per worker thread (Session isn't thread-safe)."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = common.make_session()
    return _thread_local.session


def _member_rows(row: pd.Series, infos) -> list[dict]:
    return [
        {
            "target_id": row["target_id"],
            "code": row["code"],
            "member": i.filename,
            "file_size": i.file_size,
            "compress_size": i.compress_size,
        }
        for i in infos
    ]


def backfill_reconciled(ledger: pd.DataFrame, work: Path, stage: str) -> list[dict]:
    """Rows reconciled as uploaded (found in blob after a crash) have no
    sha256/size/member inventory — rebuild those from the blob copy so the
    ledger and zip_contents carry no holes. Returns member rows to flush."""
    rows = ledger[(ledger["status"] == "uploaded") & (ledger["sha256"].isna())]
    if not len(rows):
        return []
    print(f"backfilling metadata from blob for {len(rows)} reconciled uploads")
    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=stage)
    members_all: list[dict] = []
    for target_id, row in rows.iterrows():
        data = cc.download_blob(row["blob_path"]).readall()
        try:
            infos = zipfile.ZipFile(io.BytesIO(data)).infolist()
        except zipfile.BadZipFile as e:
            print(f"WARNING {target_id}: blob copy is a bad zip ({e}) -> pending re-upload")
            ledger.loc[target_id, "status"] = "pending"
            ledger.loc[target_id, "error"] = f"blob BadZipFile: {e}"
            journal(work, transfer_record(row, stage, "blob_corrupt", error=str(e)))
            continue
        sha = hashlib.sha256(data).hexdigest()
        for col, val in {
            "sha256": sha,
            "size_bytes": len(data),
            "n_members": len(infos),
            "error": None,
            "http_status": 200,
        }.items():
            ledger.loc[target_id, col] = val
        members_all.extend(_member_rows(row, infos))
        journal(
            work,
            transfer_record(row, stage, "backfilled_from_blob", size_bytes=len(data), sha256=sha),
        )
    return members_all


def process_target(row: pd.Series, fs) -> tuple[dict, list[dict]]:
    """One target: download, inventory, upload, verify. Returns (ledger
    updates, member rows). Raises nothing for per-target upstream failures —
    they become recorded outcomes; genuine bugs propagate. Pure worker: no
    ledger/journal access (those are main-thread only)."""
    updates: dict = {"attempts": int(row["attempts"] or 0) + 1, "attempted_at": _now()}
    r = _session().get(row["url"], timeout=300)
    if r.status_code != 200:
        return updates | {
            "status": "failed_download",
            "http_status": r.status_code,
            "error": f"HTTP {r.status_code}",
        }, []
    data = r.content
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        bad = zf.testzip()
        if bad is not None:
            raise zipfile.BadZipFile(f"corrupt member {bad}")
        infos = zf.infolist()
    except zipfile.BadZipFile as e:
        return updates | {
            "status": "failed_download",
            "http_status": 200,
            "error": f"BadZipFile: {e}",
        }, []
    members = _member_rows(row, infos)
    sha = hashlib.sha256(data).hexdigest()
    try:
        blobio.upload(fs, data, row["blob_path"])
        got = fs.get_file_client(row["blob_path"]).get_file_properties().size
        if got != len(data):
            raise OSError(f"size mismatch after upload: blob={got} local={len(data)}")
    except Exception as e:  # noqa: BLE001 — recorded, visible, retryable
        return updates | {
            "status": "failed_upload",
            "error": repr(e)[:300],
            "sha256": sha,
            "size_bytes": len(data),
        }, []
    return updates | {
        "status": "uploaded",
        "http_status": 200,
        "error": None,
        "sha256": sha,
        "size_bytes": len(data),
        "n_members": len(members),
        "uploaded_at": _now(),
    }, members


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.1, help="per-worker pre-download stagger")
    ap.add_argument("--workers", type=int, default=6, help="concurrent transfers (politeness knob)")
    args = ap.parse_args(argv)

    ledger_path = args.work_dir / "products.parquet"
    if not ledger_path.exists():
        raise FileNotFoundError(f"{ledger_path} missing - run discovery.py first")
    ledger = pd.read_parquet(ledger_path).set_index("target_id", drop=False)
    ledger.index.name = None  # keep target_id addressable as a column
    ledger = common.coerce_ledger_dtypes(ledger)  # heal ledgers written pre-fix too

    ledger = reconcile_with_blob(ledger, args.stage)
    # backfill BEFORE selecting the queue: it can demote a corrupt blob to
    # pending, and that row must join THIS run's queue (else it loops forever:
    # next reconcile re-marks it uploaded, next backfill re-demotes it).
    members_backfill: list[dict] = []
    if not args.dry_run:
        members_backfill = backfill_reconciled(ledger, args.work_dir, args.stage)
    wanted = ["pending"] + (["failed_download", "failed_upload"] if args.retry_failed else [])
    todo = ledger[ledger["status"].isin(wanted)].sort_values("target_id")
    if args.limit:
        todo = todo.head(args.limit)
    print(f"targets to transfer: {len(todo)} ({ledger['status'].value_counts().to_dict()})")
    if args.dry_run:
        print(todo[["target_id", "product_class", "status", "url"]].head(30).to_string())
        return

    fs = blobio.uploader(common.global_settings(args.stage))

    def worker(row: pd.Series) -> tuple[str, dict, list[dict]]:
        time.sleep(args.sleep)
        updates, members = process_target(row, fs)
        return row["target_id"], updates, members

    # Workers are pure download->upload; the ledger, journal and checkpoints
    # are touched only here in the main thread (pandas isn't thread-safe).
    members_buf: list[dict] = members_backfill
    done = 0
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(worker, row) for _, row in todo.iterrows()]
        for fut in as_completed(futures):
            target_id, updates, members = fut.result()
            for col, val in updates.items():
                ledger.loc[target_id, col] = val
            members_buf.extend(members)
            outcome = updates["status"]
            journal(
                args.work_dir,
                transfer_record(
                    ledger.loc[target_id],
                    args.stage,
                    outcome,
                    size_bytes=updates.get("size_bytes"),
                    sha256=updates.get("sha256"),
                    error=updates.get("error"),
                ),
            )
            done += 1
            marker = "ok" if outcome == "uploaded" else f"** {outcome}: {updates.get('error')}"
            print(f"  [{done}/{len(todo)}] {target_id} {marker}", flush=True)
            if done % CHECKPOINT_EVERY == 0:
                members_buf = checkpoint(args.work_dir, ledger, members_buf, fs)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        checkpoint(args.work_dir, ledger, members_buf, fs)

    counts = ledger["status"].value_counts()
    print(f"\nfinal ledger:\n{counts.to_string()}")
    failed = ledger[ledger["status"].str.startswith("failed")]
    if len(failed):
        print(f"\nFAILURES ({len(failed)}) - rerun with --retry-failed:")
        print(failed[["target_id", "status", "http_status", "error"]].to_string())


if __name__ == "__main__":
    main()
