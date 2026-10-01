from pathlib import Path

import pytest

from gie.unosat import common, meta

ALL_META_FILES = meta.META_FILES + meta.SILVER_META_FILES


def test_bootstrap_restores_only_missing_files(tmp_path: Path):
    (tmp_path / "datasets.parquet").write_bytes(b"local-bytes")

    def fetch(path: str) -> bytes | None:
        name = path.rsplit("/", 1)[-1]
        return f"remote-{name}".encode()

    restored = meta.bootstrap_work_dir(tmp_path, fetch)

    assert (tmp_path / "datasets.parquet").read_bytes() == b"local-bytes"
    for name in ALL_META_FILES:
        if name == "datasets.parquet":
            continue
        assert (tmp_path / name).read_bytes() == f"remote-{name}".encode()
    assert sorted(restored) == sorted(n for n in ALL_META_FILES if n != "datasets.parquet")


def test_bootstrap_restores_the_silver_meta_tables(tmp_path: Path):
    """Without these a wiped work dir made silver look like it had no layers to
    process, rather than no inventory at all."""
    blobs = {
        f"{common.SILVER_META}/{name}": f"silver-{name}".encode()
        for name in meta.SILVER_META_FILES
    }
    restored = meta.bootstrap_work_dir(tmp_path, blobs.get)

    assert sorted(restored) == sorted(meta.SILVER_META_FILES)
    assert (tmp_path / "layers.parquet").read_bytes() == b"silver-layers.parquet"
    assert (tmp_path / "processing.parquet").read_bytes() == b"silver-processing.parquet"


def test_bootstrap_never_overwrites_a_local_silver_table(tmp_path: Path):
    (tmp_path / "processing.parquet").write_bytes(b"local-ledger")
    restored = meta.bootstrap_work_dir(tmp_path, lambda path: b"remote")

    assert (tmp_path / "processing.parquet").read_bytes() == b"local-ledger"
    assert "processing.parquet" not in restored


def test_bootstrap_fetch_returning_none_restores_nothing(tmp_path: Path):
    restored = meta.bootstrap_work_dir(tmp_path, lambda path: None)

    assert restored == []
    assert list(tmp_path.iterdir()) == []


def test_bootstrap_propagates_fetch_errors(tmp_path: Path):
    def fetch(path: str):
        raise OSError("blob unreachable")

    with pytest.raises(OSError):
        meta.bootstrap_work_dir(tmp_path, fetch)


def test_bootstrap_fetches_from_the_meta_prefix(tmp_path: Path):
    seen: list[str] = []

    def fetch(path: str) -> bytes | None:
        seen.append(path)
        return None

    meta.bootstrap_work_dir(tmp_path, fetch)

    assert seen == [f"{common.META}/{name}" for name in meta.META_FILES] + [
        f"{common.SILVER_META}/{name}" for name in meta.SILVER_META_FILES
    ]


class _FakeContainerClient:
    def __init__(self, blobs: dict[str, bytes]):
        self._blobs = blobs

    def download_blob(self, path: str):
        if path not in self._blobs:
            from azure.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(f"{path} not found")
        return _FakeDownload(self._blobs[path])


class _FakeDownload:
    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data


def test_blob_fetcher_maps_resource_not_found_to_none():
    cc = _FakeContainerClient({})
    fetch = meta.blob_fetcher(cc)
    assert fetch("unosat/bronze/_meta/datasets.parquet") is None


def test_blob_fetcher_returns_bytes_when_present():
    cc = _FakeContainerClient({"unosat/bronze/_meta/datasets.parquet": b"hi"})
    fetch = meta.blob_fetcher(cc)
    assert fetch("unosat/bronze/_meta/datasets.parquet") == b"hi"


def test_blob_fetcher_does_not_swallow_other_errors():
    class _BoomContainerClient:
        def download_blob(self, path: str):
            raise RuntimeError("boom")

    fetch = meta.blob_fetcher(_BoomContainerClient())
    with pytest.raises(RuntimeError):
        fetch("unosat/bronze/_meta/datasets.parquet")


def test_default_work_dir_honours_env_var(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GIE_WORK_DIR", str(tmp_path / "custom"))
    assert common.default_work_dir() == tmp_path / "custom"


def test_default_work_dir_defaults_under_platformdirs(monkeypatch):
    monkeypatch.delenv("GIE_WORK_DIR", raising=False)
    assert common.default_work_dir().name == "unosat_archive"
