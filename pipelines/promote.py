"""Promote the working served tiers to the published (prod) copy — the publish gate.

The cheap prod/dev split (no separate storage account): the pipeline writes the
WORKING ``gold/`` + ``platinum/`` (what staging reads); this copies them to
``gold-prod/`` + ``platinum-prod/`` (what the prod app slot reads, via
``GIE_TIER=prod``). A gold/platinum refresh is therefore invisible to prod until
you run this. Copies are **server-side within the one account** (Azure
``start_copy_from_url``) — near-instant, and no data leaves Azure.

Only the served tiers are split; ``bronze``/``silver`` stay a single shared copy
(a few secondary server-rendered layers still read silver directly — known
residual, see the handover). Copies OVERWRITE the published blob; stale published
blobs (a source file removed/renamed) are not pruned yet.

Run:  GIE_BLOB_ACCOUNT_PREFIX=... uv run --group etl python pipelines/promote.py [--dry-run]
"""

from __future__ import annotations

import sys

import ocha_stratus as stratus
from azure.storage.blob import BlobServiceClient

from gie.config import load_settings

# (working prefix -> published prefix). Mirrors config._served's "-prod" suffix.
TIERS = [("gold", "gold-prod"), ("platinum", "platinum-prod")]


def main() -> None:
    dry = "--dry-run" in sys.argv
    # Always promote FROM the working (dev) copy, regardless of any ambient GIE_TIER.
    s = load_settings("dev")
    account_url = f"https://{s.account_host}"
    read_sas = s.sas_token()  # source reads (server-side copy needs the source readable)
    dst_cc = BlobServiceClient(
        account_url, credential=s.sas_token(write=True)
    ).get_container_client(s.container)

    grand = 0
    for src_prefix, dst_prefix in TIERS:
        base = f"{s.project_prefix}/{src_prefix}/"
        names = list(
            stratus.list_container_blobs(
                name_starts_with=base, stage="dev", container_name=s.container
            )
        )
        print(f"{src_prefix}/ -> {dst_prefix}/  ({len(names)} blobs){'  [dry-run]' if dry else ''}")
        for name in names:
            dst = f"{s.project_prefix}/{dst_prefix}/{name[len(base):]}"
            if dry:
                continue
            src_url = f"{account_url}/{s.container}/{name}?{read_sas}"
            dst_cc.get_blob_client(dst).start_copy_from_url(src_url)
            grand += 1

    if dry:
        print("dry-run: nothing copied.")
        return
    # Sanity check: published blob counts should match the working counts.
    for src_prefix, dst_prefix in TIERS:
        n_src = len(list(stratus.list_container_blobs(
            name_starts_with=f"{s.project_prefix}/{src_prefix}/", stage="dev", container_name=s.container)))
        n_dst = len(list(stratus.list_container_blobs(
            name_starts_with=f"{s.project_prefix}/{dst_prefix}/", stage="dev", container_name=s.container)))
        flag = "OK" if n_dst >= n_src else "MISMATCH"
        print(f"  {dst_prefix}/: {n_dst} published vs {n_src} working  [{flag}]")
    print(f"done: {grand} blobs promoted to *-prod.")


if __name__ == "__main__":
    main()
