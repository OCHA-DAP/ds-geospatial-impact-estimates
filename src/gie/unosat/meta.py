"""Bootstrap the local work dir from its blob `_meta/` copy.

The blob copy at ``unosat/bronze/_meta/`` is the durable record (harvest
checkpoints it there every 25 transfers, see ``harvest.checkpoint``). A
missing local work dir — a reboot wiped `/tmp`, or a colleague's laptop with
no prior run — is not a fresh-start signal; it is restored from blob before
anything reads a local file, so a lost work dir costs nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import ocha_stratus as stratus
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
        common.atomic_write(dest, data)
        restored.append(name)
    return restored


def bootstrap(work_dir: Path, stage: str):
    """What every unosat CLI does before it reads a local file: make the work
    dir, open the ``global`` container, restore whatever ``_meta/`` files are
    missing locally, and report what came back. Returns the container client,
    which the callers also use for downloads and listings."""
    work_dir.mkdir(parents=True, exist_ok=True)
    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=stage)
    restored = bootstrap_work_dir(work_dir, blob_fetcher(cc))
    if restored:
        print(f"bootstrapped from blob: {restored}")
    return cc


def blob_fetcher(container_client) -> Callable[[str], bytes | None]:
    """Wrap ``container_client.download_blob(name).readall()``, mapping only
    a missing blob to ``None``; any other failure propagates."""

    def fetch(name: str) -> bytes | None:
        try:
            return container_client.download_blob(name).readall()
        except ResourceNotFoundError:
            return None

    return fetch
