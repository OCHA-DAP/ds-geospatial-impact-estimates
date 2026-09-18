"""Extract coded-value domains from every uploaded geodatabase in bronze.

Reads each distinct GDB content once (through the local cache; fetched from
blob if absent), writes {work_dir}/domains.parquet and domains_status.parquet
and uploads both to unosat/bronze/_meta/. Resumable: sha256 values already in
domains_status are skipped.

Run:  uv run --group etl --group api python pipelines/unosat/domains.py [--stage dev] [--limit N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd

from gie import blobio
from gie.unosat import cache, common, domains

# Checkpoint frequency: persist every N GDBs so a kill mid-batch loses at most
# this many GDBs' worth of re-work, never silently drops already-done work.
CHECKPOINT_EVERY = 25


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    led = pd.read_parquet(args.work_dir / "resources.parquet")
    gdbs = led[(led["format"] == "Geodatabase") & led["status"].isin(common.UPLOADED_STATUSES)]
    gdbs = gdbs.drop_duplicates("sha256")
    status_path = args.work_dir / "domains_status.parquet"
    done = (
        pd.read_parquet(status_path) if status_path.exists() else pd.DataFrame(columns=["sha256"])
    )
    todo = gdbs[~gdbs["sha256"].isin(done["sha256"])]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"distinct GDBs: {len(gdbs)}, to process: {len(todo)}")

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    all_rows: list[dict] = []
    statuses: list[dict] = []
    try:
        for i, r in enumerate(todo.itertuples(), 1):
            path = cache.read_through(
                r.sha256, r.resource_name,
                lambda r=r: cc.download_blob(common.blob_path(r.sha256, r.resource_name)).readall(),
            )
            rows, status = domains.domains_for_gdb_zip(r.sha256, path)
            all_rows.extend(rows)
            statuses.append(domains.status_row(r.sha256, status, len(rows)))
            print(f"  [{i}/{len(todo)}] {r.resource_name} {status} ({len(rows)} rows)", flush=True)
            if i % CHECKPOINT_EVERY == 0:
                domains.persist(args.work_dir, all_rows, statuses)
                all_rows, statuses = [], []
    finally:
        # Persists whatever completed before a Ctrl-C or an exception, so
        # interrupted runs never lose already-processed GDBs.
        if statuses or all_rows:
            domains.persist(args.work_dir, all_rows, statuses)

    if len(todo):
        fs = blobio.uploader(common.global_settings(args.stage))
        for name in ("domains.parquet", "domains_status.parquet"):
            blobio.upload(fs, (args.work_dir / name).read_bytes(), f"{common.META}/{name}")
    if status_path.exists():
        print(pd.read_parquet(status_path)["status"].value_counts().to_string())
    else:
        print("nothing processed")


if __name__ == "__main__":
    main()
