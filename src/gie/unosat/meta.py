"""Bootstrap the local work dir from its blob `_meta/` copy.

The blob copy at ``unosat/bronze/_meta/`` is the durable record (harvest
checkpoints it there every 25 transfers, see ``harvest.checkpoint``). A
missing local work dir — a reboot wiped `/tmp`, or a colleague's laptop with
no prior run — is not a fresh-start signal; it is restored from blob before
anything reads a local file, so a lost work dir costs nothing.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError

from gie.unosat import common

META_FILES = (
    "datasets.parquet",
    "resources.parquet",
    "zip_contents.parquet",
    "transfers.jsonl",
    "domains.parquet",
    "domains_status.parquet",
)


def bootstrap_work_dir(work_dir: Path, fetch: Callable[[str], bytes | None]) -> list[str]:
    """For each ``META_FILES`` name missing locally, call
    ``fetch(f"{common.META}/{name}")``; when it returns bytes, write them to
    ``work_dir/name`` atomically (temp file + ``os.replace``). Never
    overwrite a file that already exists locally. ``fetch`` returning
    ``None`` (blob absent, a normal state on a first-ever run) restores
    nothing for that name; any other exception propagates. Returns the
    names actually restored."""
    restored: list[str] = []
    for name in META_FILES:
        dest = work_dir / name
        if dest.exists():
            continue
        data = fetch(f"{common.META}/{name}")
        if data is None:
            continue
        fd, tmp = tempfile.mkstemp(dir=work_dir, prefix=name + ".", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        restored.append(name)
    return restored


def blob_fetcher(container_client) -> Callable[[str], bytes | None]:
    """Wrap ``container_client.download_blob(name).readall()``, mapping only
    a missing blob to ``None``; any other failure propagates."""

    def fetch(name: str) -> bytes | None:
        try:
            return container_client.download_blob(name).readall()
        except ResourceNotFoundError:
            return None

    return fetch
