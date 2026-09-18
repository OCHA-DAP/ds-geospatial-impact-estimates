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


def test_read_through_disabled_uses_temp_and_still_returns_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    p = cache.read_through("d" * 64, "A.zip", lambda: b"x", enabled=False)
    assert p.read_bytes() == b"x"
    assert not (tmp_path / "unosat").exists()  # nothing persisted under the cache


def test_read_through_writes_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))

    def bad_fetch() -> bytes:
        raise OSError("network")

    with pytest.raises(OSError):
        cache.read_through("e" * 64, "A.zip", bad_fetch)
    target = cache.cache_path("e" * 64, "A.zip")
    assert not target.exists()
    assert not list(Path(target.parent).glob("*.part")) if target.parent.exists() else True
