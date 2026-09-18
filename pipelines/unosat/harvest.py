"""Transfer every pending ledger row into content-addressed bronze:
download -> testzip -> inventory -> upload (unless content already there) -> record.

Resume model: the blob store is truth. Every run reconciles the ledger against
a listing of bronze; already-uploaded content is skipped; ledger rows claiming
uploaded whose object is gone are demoted (loudly). Ledger + journal
checkpoint locally AND to blob every 25 items and on exit (incl. Ctrl-C).
Terminal upstream states (unavailable_404, corrupt_upstream) are never
retried; --retry-failed re-attempts failed_download / failed_upload.

Run:  uv run --group etl --group api python pipelines/unosat/harvest.py
      [--limit N] [--stage dev] [--retry-failed] [--dry-run] [--workers 6] [--no-cache]
      [--scope flood|other|unknown ...]
"""

from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd

from gie import blobio
from gie.unosat import common, harvest
from gie.unosat.store import DataLakeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--per-host", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.1, help="per-worker pre-download stagger")
    ap.add_argument(
        "--no-cache", action="store_true", help="do not keep downloads in the local cache"
    )
    ap.add_argument("--scope", nargs="*", default=None, help="restrict to ledger scopes")
    args = ap.parse_args(argv)

    ledger_path = args.work_dir / "resources.parquet"
    if not ledger_path.exists():
        raise FileNotFoundError(f"{ledger_path} missing - run discovery.py first")
    ledger = pd.read_parquet(ledger_path).set_index("target_id", drop=False)
    ledger.index.name = None
    ledger = common.coerce_ledger_dtypes(ledger)

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    fs = blobio.uploader(common.global_settings(args.stage))
    store = DataLakeStore(fs, cc)

    ledger = harvest.reconcile_with_blob(ledger, store)
    wanted = ["pending"] + (sorted(common.RETRYABLE_STATUSES) if args.retry_failed else [])
    todo = ledger[ledger["status"].isin(wanted)]
    if args.scope:
        todo = todo[todo["scope"].isin(args.scope)]
    todo = todo.sort_values(["scope", "target_id"])
    if args.limit:
        todo = todo.head(args.limit)
    print(f"targets to transfer: {len(todo)} ({ledger['status'].value_counts().to_dict()})")
    if args.dry_run:
        print(todo[["target_id", "resource_name", "format", "host", "status"]].head(30).to_string())
        return

    limiter = common.HostLimiter(args.per_host)
    local = threading.local()

    def session():
        if not hasattr(local, "s"):
            local.s = common.make_session()
        return local.s

    def worker(row: pd.Series):
        time.sleep(args.sleep)
        updates, members = harvest.process_target(
            row, session=session(), store=store, limiter=limiter, use_cache=not args.no_cache
        )
        return row["target_id"], updates, members

    members_buf: list[dict] = []
    done = 0
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(worker, row) for _, row in todo.iterrows()]
        for fut in as_completed(futures):
            target_id, updates, members = fut.result()  # bugs propagate here
            harvest.apply_updates(ledger, target_id, updates)
            members_buf.extend(members)
            outcome = updates["status"]
            harvest.journal(
                args.work_dir,
                harvest.transfer_record(
                    ledger.loc[target_id], args.stage, outcome,
                    size_bytes=updates.get("size_bytes"), sha256=updates.get("sha256"),
                    error=updates.get("error"),
                ),
            )
            done += 1
            ok = outcome in common.UPLOADED_STATUSES
            marker = outcome if ok else f"** {outcome}: {updates.get('error')}"
            print(f"  [{done}/{len(todo)}] {target_id} {marker}", flush=True)
            if done % harvest.CHECKPOINT_EVERY == 0:
                members_buf = harvest.checkpoint(args.work_dir, ledger, members_buf, store)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        harvest.checkpoint(args.work_dir, ledger, members_buf, store)

    counts = ledger["status"].value_counts()
    print(f"\nfinal ledger:\n{counts.to_string()}")
    failed = ledger[ledger["status"].isin(common.RETRYABLE_STATUSES)]
    if len(failed):
        print(f"\nFAILURES ({len(failed)}) - rerun with --retry-failed:")
        print(failed[["target_id", "status", "http_status", "error"]].to_string())
    terminal = ledger[ledger["status"].isin(common.TERMINAL_STATUSES)]
    if len(terminal):
        print(f"\nUPSTREAM UNAVAILABLE ({len(terminal)}) - recorded, not retried:")
        print(terminal[["target_id", "status", "error"]].to_string())


if __name__ == "__main__":
    main()
