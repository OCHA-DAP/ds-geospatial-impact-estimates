"""Build/refresh the UNOSAT harvest ledger from HDX.

Writes {work_dir}/datasets.parquet and {work_dir}/resources.parquet (THE
LEDGER). Re-running merges onto the existing ledger: transfer outcomes are
preserved, new or re-published resources become pending, vanished ones are
flagged missing_upstream, never dropped.

Run:  uv run --group etl --group api python pipelines/unosat/discovery.py [--work-dir ...]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from gie.unosat import discovery


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    args = ap.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    print("fetching UNOSAT datasets from HDX ...")
    datasets = discovery.fetch_unosat_datasets()
    ds_table = discovery.datasets_table(datasets)
    ledger = discovery.resources_ledger(datasets)
    print(f"datasets: {len(ds_table)}  resources: {len(ledger)}")

    ledger_path = args.work_dir / "resources.parquet"
    if ledger_path.exists():
        old = pd.read_parquet(ledger_path)
        ledger = discovery.merge_ledgers(ledger, old)
        print(f"merged onto existing ledger ({len(old)} rows)")
    ds_table.to_parquet(args.work_dir / "datasets.parquet")
    ledger.to_parquet(ledger_path)

    print(f"\nledger: {len(ledger)} rows -> {ledger_path}")
    print(ledger["status"].value_counts().to_string())
    print("\npending by scope / format:")
    print(ledger[ledger.status == "pending"].groupby(["scope", "format"]).size().to_string())
    print("\nhosts:", ledger.host.value_counts().to_dict())


if __name__ == "__main__":
    main()
