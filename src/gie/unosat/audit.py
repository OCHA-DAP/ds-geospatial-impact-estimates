"""Bronze invariants (spec §5, B-rules). Each check returns (ok, detail)."""

from __future__ import annotations

import pandas as pd

from gie.unosat import common
from gie.unosat.store import BlobStore


def check_b1_no_pending(ledger: pd.DataFrame) -> tuple[bool, str]:
    n = int((ledger["status"] == "pending").sum())
    return n == 0, f"{n} pending"


def check_b2_census(ledger: pd.DataFrame, store: BlobStore) -> tuple[bool, str]:
    """Every uploaded row's (sha256, basename) exists with the recorded size,
    and every object under bronze/blob= is claimed by some uploaded row."""
    up = ledger[ledger["status"].isin(common.UPLOADED_STATUSES)]
    expected = {
        common.blob_path(r.sha256, r.resource_name): int(r.size_bytes) for r in up.itertuples()
    }
    got = store.list_sizes(f"{common.BRONZE}/blob=")
    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    wrong = sorted(p for p in set(expected) & set(got) if expected[p] != got[p])
    ok = not (missing or extra or wrong)
    detail = (
        f"{len(got)} objects; missing={len(missing)} extra={len(extra)} "
        f"size-mismatch={len(wrong)}"
    )
    if not ok:
        detail += (
            f" | missing[:3]={missing[:3]} extra[:3]={extra[:3]} "
            f"size[:3]={wrong[:3]}"
        )
    return ok, detail


def check_b3_domains(
    ledger: pd.DataFrame, status_df: pd.DataFrame
) -> tuple[bool, str]:
    gdb = ledger[
        (ledger["format"] == "Geodatabase") & ledger["status"].isin(common.UPLOADED_STATUSES)
    ]
    want = set(gdb["sha256"].dropna())
    have = set(status_df["sha256"]) if len(status_df) else set()
    missing = sorted(want - have)
    return (
        not missing,
        f"{len(want)} GDBs; without domain status: {len(missing)} {missing[:3]}",
    )


def run_bronze_checks(
    ledger: pd.DataFrame, store: BlobStore, status_df: pd.DataFrame
) -> bool:
    ok = True
    for name, (passed, detail) in {
        "B1 no pending targets": check_b1_no_pending(ledger),
        "B2 blob census matches ledger (paths+sizes, both directions)": check_b2_census(
            ledger, store
        ),
        "B3 every uploaded GDB has a domains status": check_b3_domains(ledger, status_df),
    }.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")
        ok &= passed
    return ok
