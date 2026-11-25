"""Invariant checks for the CEMS flood archive (bronze) and its silver layer.

Run after any harvest, silver build, or defect fix. Prints a pass/fail report
and writes {work_dir}/audit_stale_codes.txt: the activation codes whose
silver partitions violate a rule and need reprocessing. The defect-fix loop
is always:

    1. fix the rule/code (silver.py, common.py, ...)
    2. uv run ... audit.py                       -> writes audit_stale_codes.txt
    3. uv run ... silver.py --codes $(cat /tmp/gie_cems_flood_archive/audit_stale_codes.txt)
    4. uv run ... audit.py                       -> must pass clean

Checks:
  bronze   B1 no pending targets; B2 blob census == ledger (names AND sizes)
  silver   S1 processing ledger covers every uploaded zip exactly once
           S2 every uploaded code has observed_event + coverage partitions
           S3 acq_datetime plausible (2011 <= year <= now, when present)
           S4 acq_precision/method values within the documented vocabulary
           S5 rows with precision != window carry acq_datetime;
              window rows carry acq_window_end

Exit code 1 on any failure (S-rule failures also land in the stale list).
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import UTC, datetime
from pathlib import Path

import common
import ocha_stratus as stratus
import pandas as pd

SILVER = "copernicus_ems/flood/silver"
PRECISIONS = {"minute", "date", "window"}
METHODS = {"attribute", "source_table", "api", "api_window", "window"}
ACQ_COLS = ["acq_datetime", "acq_window_end", "acq_precision", "acq_method"]


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--skip-bronze", action="store_true", help="silver rules only (faster)")
    args = ap.parse_args(argv)

    led = pd.read_parquet(args.work_dir / "products.parquet")
    up = led[led.status == "uploaded"]
    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    ok = True

    if not args.skip_bronze:
        print("bronze:")
        ok &= check("B1 no pending targets", (led.status == "pending").sum() == 0)
        sizes = {
            b.name: b.size
            for b in cc.list_blobs(name_starts_with=f"{common.BRONZE}/code=")
            if b.name.endswith(".zip")
        }
        same_names = set(sizes) == set(up.blob_path)
        same_sizes = same_names and all(
            int(r.size_bytes) == sizes[r.blob_path] for r in up.itertuples()
        )
        ok &= check(
            "B2 blob census matches ledger (names+sizes)",
            same_names and same_sizes,
            f"{len(sizes)} zips",
        )

    print("silver:")
    proc = pd.read_parquet(args.work_dir / "silver_processing.parquet")
    covered = set(proc.target_id) == set(up.target_id) and not proc.target_id.duplicated().any()
    ok &= check(
        "S1 processing ledger == uploaded zips", covered, str(proc.status.value_counts().to_dict())
    )

    def partition_codes(table: str) -> set[str]:
        return {
            b.name.split("code=")[1].split("/")[0]
            for b in cc.list_blobs(name_starts_with=f"{SILVER}/{table}/code=")
        }

    want = set(up.code.unique())
    oe_codes, cov_codes = partition_codes("observed_event"), partition_codes("coverage")
    ok &= check(
        "S2 partitions exist for every code",
        oe_codes == want and cov_codes == want,
        f"missing={sorted(want - (oe_codes & cov_codes))}",
    )

    stale: set[str] = want - (oe_codes & cov_codes)
    now = datetime.now(UTC).replace(tzinfo=None)
    n_rows = 0
    for i, code in enumerate(sorted(want & oe_codes)):
        raw = cc.download_blob(f"{SILVER}/observed_event/code={code}/data.parquet").readall()
        df = pd.read_parquet(io.BytesIO(raw), columns=ACQ_COLS)
        n_rows += len(df)
        if not len(df):
            continue
        bad = []
        yr = pd.to_datetime(df.acq_datetime).dt.year
        if ((yr < 2011) | (pd.to_datetime(df.acq_datetime) > now)).any():
            bad.append("S3 implausible acq_datetime")
        if (
            not set(df.acq_precision.dropna()) <= PRECISIONS
            or not set(df.acq_method.dropna()) <= METHODS
        ):
            bad.append("S4 unknown precision/method value")
        exact = df.acq_precision != "window"
        if (
            df.loc[exact, "acq_datetime"].isna().any()
            or df.loc[~exact, "acq_window_end"].isna().any()
        ):
            bad.append("S5 missing datetime/window bound")
        if bad:
            print(f"    {code}: {', '.join(bad)}")
            stale.add(code)
        if (i + 1) % 50 == 0:
            print(f"    ... scanned {i + 1}/{len(want)}")

    ok &= check(
        "S3-S5 row rules across all partitions",
        not stale,
        f"{n_rows:,} rows scanned; stale codes: {len(stale)}",
    )

    out = args.work_dir / "audit_stale_codes.txt"
    out.write_text(",".join(sorted(stale)))
    print(f"\nstale codes -> {out}" + (" (empty)" if not stale else f": {sorted(stale)}"))
    if not ok:
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
