"""Local mirror of the content-addressed bronze layout (spec §2b).

Because paths are keyed by sha256 the cache is never stale: a file exists at
its hash path or it does not. Harvest writes through; silver reads through.
Blob is the source of truth; this directory is disposable.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from platformdirs import user_cache_dir

from gie.unosat import common


def cache_root() -> Path:
    env = os.getenv("GIE_CACHE_DIR")
    return Path(env) if env else Path(user_cache_dir("gie"))


def cache_path(sha256: str, basename: str) -> Path:
    return cache_root() / common.blob_path(sha256, basename)


def read_through(
    sha256: str, basename: str, fetch: Callable[[], bytes], *, enabled: bool = True
) -> Path:
    """Return a local file holding the content for ``sha256``/``basename``,
    calling ``fetch`` only when it is not already cached. Writes are atomic
    (temp file + rename) so a killed run never leaves a truncated file at
    the final path. With ``enabled=False`` the bytes go to a temp file
    outside the cache (caller owns cleanup)."""
    if not enabled:
        fd, tmp = tempfile.mkstemp(suffix=basename)
        with os.fdopen(fd, "wb") as f:
            f.write(fetch())
        return Path(tmp)
    dest = cache_path(sha256, basename)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    common.atomic_write(dest, fetch())
    return dest
