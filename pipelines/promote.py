"""Promote the working served tiers to the published (prod) copy — the publish gate.

The cheap prod/dev split (no separate storage account): the pipeline writes the
WORKING ``gold/`` + ``platinum/`` (what staging reads); this copies them to
``gold-prod/`` + ``platinum-prod/`` (what the prod app slot reads, via
``GIE_TIER=prod``). A gold/platinum refresh is therefore invisible to prod until
you run this.

Copies are **server-side** (Azure ``Copy Blob`` blob->blob within the one
account) — the data never travels through this machine, so it's near-instant
regardless of file size. HNS/ADLS-Gen2 caveats handled: list files only (skip
0-byte directory markers), and pre-create the destination directory (a
server-side copy target dir must exist).

Only the served tiers are split; ``bronze``/``silver`` stay a single shared copy
(a few secondary server-rendered layers still read silver directly — known
residual, see the handover). Copies OVERWRITE the published file; stale published
files (a source file removed/renamed) are not pruned yet. Re-runnable: already
promoted files (same size) are skipped.

Run:  GIE_BLOB_ACCOUNT_PREFIX=... uv run --group etl python pipelines/promote.py [--dry-run]
"""

from __future__ import annotations

import sys
import time

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from azure.storage.filedatalake import DataLakeServiceClient

from gie.config import load_settings

# (working prefix -> published prefix). Mirrors config._served's "-prod" suffix.
TIERS = [("gold", "gold-prod"), ("platinum", "platinum-prod")]


def _files(fs, prefix: str, project_prefix: str) -> dict[str, int]:
    """Files under a tier -> size (skip HNS directory markers). {} if the tier is absent."""
    try:
        return {
            p.name: p.content_length
            for p in fs.get_paths(path=f"{project_prefix}/{prefix}", recursive=True)
            if not p.is_directory
        }
    except ResourceNotFoundError as e:  # tier truly absent is the only acceptable miss
        print(f"  {prefix}/: listing failed ({e}); treating as absent")
        return {}
    except Exception as e:
        raise RuntimeError(
            f"listing {project_prefix}/{prefix}/ failed (not a not-found error — "
            f"treating as a real failure, not an absent tier): {e}"
        ) from e


def main() -> None:
    dry = "--dry-run" in sys.argv
    # Always promote FROM the working (dev) copy, regardless of any ambient GIE_TIER.
    s = load_settings("dev")
    blob_url = f"https://{s.account_host}"
    dfs_url = f"https://{s.account_name}.dfs.core.windows.net"
    read_sas = s.sas_token()  # source reads for the server-side copy
    src_fs = DataLakeServiceClient(dfs_url, credential=read_sas).get_file_system_client(s.container)
    dst_fs = DataLakeServiceClient(dfs_url, credential=s.sas_token(write=True)).get_file_system_client(s.container)
    dst_blob = BlobServiceClient(blob_url, credential=s.sas_token(write=True))

    copied = skipped = 0
    for src_prefix, dst_prefix in TIERS:
        base = f"{s.project_prefix}/{src_prefix}/"
        src = _files(src_fs, src_prefix, s.project_prefix)
        done = _files(dst_fs, dst_prefix, s.project_prefix)  # resume: skip same-size
        print(f"{src_prefix}/ -> {dst_prefix}/  ({len(src)} files){'  [dry-run]' if dry else ''}")
        made_dirs: set[str] = set()
        for name, size in sorted(src.items()):
            dst = f"{s.project_prefix}/{dst_prefix}/{name[len(base):]}"
            if done.get(dst) == size:
                skipped += 1
                continue
            if dry:
                continue
            dpath = dst.rsplit("/", 1)[0]  # HNS: the copy target dir must exist
            if dpath not in made_dirs:
                try:
                    dst_fs.create_directory(dpath)
                except ResourceExistsError:
                    pass
                made_dirs.add(dpath)
            bc = dst_blob.get_blob_client(s.container, dst)
            bc.start_copy_from_url(f"{blob_url}/{s.container}/{name}?{read_sas}")
            status = "pending"
            for _ in range(120):  # same-account copy is near-instant; guard anyway
                status = bc.get_blob_properties().copy.status
                if status != "pending":
                    break
                time.sleep(0.5)
            if status != "success":
                raise RuntimeError(f"copy failed ({status}): {dst}")
            copied += 1

    if dry:
        print("dry-run: nothing copied.")
        return
    for src_prefix, dst_prefix in TIERS:
        n_src = len(_files(src_fs, src_prefix, s.project_prefix))
        n_dst = len(_files(dst_fs, dst_prefix, s.project_prefix))
        flag = "OK" if n_dst >= n_src else "MISMATCH"
        print(f"  {dst_prefix}/: {n_dst} published vs {n_src} working  [{flag}]")
    print(f"done: {copied} files promoted ({skipped} already current).")


if __name__ == "__main__":
    main()
