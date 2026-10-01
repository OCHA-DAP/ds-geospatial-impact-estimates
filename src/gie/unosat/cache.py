"""Local mirror of the content-addressed bronze layout (spec §2b).

Because paths are keyed by sha256 the cache is never stale: a file exists at
its hash path or it does not. Harvest writes through; silver reads through.
Blob is the source of truth; this directory is disposable.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from platformdirs import user_cache_dir

from gie.unosat import common


def cache_root() -> Path:
    env = os.getenv("GIE_CACHE_DIR")
    return Path(env) if env else Path(user_cache_dir("gie"))


def cache_path(sha256: str, basename: str) -> Path:
    return cache_root() / common.blob_path(sha256, basename)


def read_through(sha256: str, basename: str, fetch: Callable[[], bytes]) -> Path:
    """Return a local file holding the content for ``sha256``/``basename``,
    calling ``fetch`` only when it is not already cached. The write is atomic
    (temp file + rename) so a killed run never leaves a truncated file at the
    final path. Harvest's ``--no-cache`` does not come through here: it keeps
    its own temp file and never consults the cache."""
    dest = cache_path(sha256, basename)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    common.atomic_write(dest, fetch())
    return dest
