"""Invariant checks for the UNOSAT bronze archive. Exit 1 on any failure.

Run:  uv run --group etl --group api python pipelines/unosat/audit.py [--stage dev]
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from gie import blobio
from gie.unosat import audit, common, meta
from gie.unosat.store import DataLakeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    args = ap.parse_args(argv)

    cc = meta.bootstrap(args.work_dir, args.stage)

    ledger = common.coerce_ledger_dtypes(pd.read_parquet(args.work_dir / "resources.parquet"))
    status_path = args.work_dir / "domains_status.parquet"
    status_df = (
        pd.read_parquet(status_path)
        if status_path.exists()
        else pd.DataFrame(columns=["sha256", "status"])
    )
    store = DataLakeStore(blobio.uploader(common.global_settings(args.stage)), cc)

    print("bronze:")
    ok = audit.run_bronze_checks(ledger, store, status_df)
    print(f"domains status breakdown: {status_df.status.value_counts().to_dict()}")
    print("\nledger statuses:", ledger["status"].value_counts().to_dict())
    if not ok:
        sys.exit(1)
    print("ALL BRONZE CHECKS PASSED")


if __name__ == "__main__":
    main()
