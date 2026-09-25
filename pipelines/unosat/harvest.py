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

import pandas as pd

from gie import blobio
from gie.unosat import common, harvest, meta
from gie.unosat.store import DataLakeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
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

    cc = meta.bootstrap(args.work_dir, args.stage)

    ledger_path = args.work_dir / "resources.parquet"
    if not ledger_path.exists():
        raise FileNotFoundError(
            f"{ledger_path} missing - run discovery.py first (the work dir bootstraps from "
            "blob automatically when the archive already exists)"
        )
    ledger = pd.read_parquet(ledger_path).set_index("target_id", drop=False)
    ledger.index.name = None
    ledger = common.coerce_ledger_dtypes(ledger)

    fs = blobio.uploader(common.global_settings(args.stage))
    store = DataLakeStore(fs, cc)

    ledger = harvest.reconcile_with_blob(ledger, store)

    # Computed in both modes (for the summary line below), but only applied
    # and journaled for a real run: --dry-run must not mutate the ledger or
    # append to transfers.jsonl, or the next real run re-settles and
    # re-journals the same rows.
    settled = harvest.settle_url_siblings(ledger)
    if not args.dry_run:
        for target_id, updates in settled:
            harvest.record_outcome(
                ledger, args.work_dir, args.stage, target_id, updates, [], via="url_sibling"
            )

    wanted = ["pending"] + (sorted(common.RETRYABLE_STATUSES) if args.retry_failed else [])
    todo = ledger[ledger["status"].isin(wanted)]
    if args.scope:
        todo = todo[todo["scope"].isin(args.scope)]
    todo = todo.sort_values(["scope", "target_id"])
    if args.limit:
        todo = todo.head(args.limit)

    reps, siblings = harvest.representatives(todo)
    counts = ledger["status"].value_counts().to_dict()
    print(
        f"targets to transfer: {len(reps)} representative URLs covering {len(todo)} rows; "
        f"{len(settled)} settled from already-uploaded URLs (ledger: {counts})"
    )
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
    since_checkpoint = 0

    def checkpoint_if_due() -> None:
        nonlocal members_buf, since_checkpoint
        if since_checkpoint >= harvest.CHECKPOINT_EVERY:
            members_buf = harvest.checkpoint(args.work_dir, ledger, members_buf, store)
            since_checkpoint = 0

    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(worker, row) for _, row in reps.iterrows()]
        for fut in as_completed(futures):
            target_id, updates, members = fut.result()  # bugs propagate here
            members_buf.extend(
                harvest.record_outcome(
                    ledger, args.work_dir, args.stage, target_id, updates, members
                )
            )
            done += 1
            since_checkpoint += 1
            print(f"  [{done}/{len(todo)}] {target_id} {harvest.outcome_marker(updates)}",
                  flush=True)
            checkpoint_if_due()

            sibling_ids = siblings.get(target_id, [])
            if sibling_ids:
                members_buf.extend(
                    harvest.propagate_to_siblings(
                        ledger, args.work_dir, args.stage, updates, members, sibling_ids
                    )
                )
                # Every sibling of a representative gets the same outcome, so
                # one marker covers the whole group.
                sib_marker = harvest.outcome_marker(
                    harvest.sibling_updates(updates, [], sibling_ids[0])[0]
                )
                for sibling_id in sibling_ids:
                    done += 1
                    since_checkpoint += 1
                    print(f"  [{done}/{len(todo)}] {sibling_id} {sib_marker} (via {target_id})",
                          flush=True)
                    checkpoint_if_due()
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
