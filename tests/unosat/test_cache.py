import threading
from pathlib import Path

import pytest

from gie.unosat import cache


def test_cache_root_prefers_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path / "custom"))
    assert cache.cache_root() == tmp_path / "custom"


def test_cache_root_defaults_to_platformdirs(monkeypatch):
    monkeypatch.delenv("GIE_CACHE_DIR", raising=False)
    root = cache.cache_root()
    assert root.name == "gie"


def test_cache_path_mirrors_bronze_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    sha = "b" * 64
    expected = tmp_path / "unosat" / "bronze" / f"blob={sha}" / "X.zip"
    assert cache.cache_path(sha, "X.zip") == expected


def test_read_through_fetches_once_then_hits(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    def fetch() -> bytes:
        calls["n"] += 1
        return b"zipbytes"

    p1 = cache.read_through("c" * 64, "A.zip", fetch)
    p2 = cache.read_through("c" * 64, "A.zip", fetch)
    assert p1 == p2 and p1.read_bytes() == b"zipbytes"
    assert calls["n"] == 1


def test_read_through_writes_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))

    def bad_fetch() -> bytes:
        raise OSError("network")

    with pytest.raises(OSError):
        cache.read_through("e" * 64, "A.zip", bad_fetch)
    target = cache.cache_path("e" * 64, "A.zip")
    assert not target.exists()
    assert not list(Path(target.parent).glob("*.part")) if target.parent.exists() else True


def test_read_through_concurrent_writers_unique_temp_files(monkeypatch, tmp_path):
    """Concurrent callers for same (sha256, basename) use unique temp files."""
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    sha = "f" * 64
    basename = "concurrent.zip"
    payload = bytes([42]) * (1 << 20)  # 1 MiB of all 42s
    num_threads = 4
    results = []

    def fetch() -> bytes:
        return payload

    def worker():
        p = cache.read_through(sha, basename, fetch)
        results.append(p)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads got the same path
    assert all(p == results[0] for p in results)
    # File exists and has correct content
    assert results[0].read_bytes() == payload
    # No .part files left behind
    cache_dir = cache.cache_path(sha, basename).parent
    assert not list(cache_dir.glob("*.part"))
