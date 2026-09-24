"""Blob store boundary so the harvest worker is testable without Azure.

``DataLakeStore`` is the real thing: uploads via gie.blobio (chunked DFS path,
the documented fix for single-PUT timeouts on this lake) and existence/size
checks via the same filesystem client. ``MemoryStore`` is for tests.
"""

from __future__ import annotations

from typing import Protocol

from gie import blobio


def drop_directory_entries(sizes: dict[str, int]) -> dict[str, int]:
    """Drop keys that are a strict path-prefix of another key.

    On a hierarchical-namespace (ADLS Gen2) account, listing returns one
    zero-byte entry per directory in addition to the file entries under it;
    those directory placeholders aren't objects we archived and must not be
    counted as such.
    """
    keys = list(sizes)
    return {
        k: v
        for k, v in sizes.items()
        if not any(other.startswith(k + "/") for other in keys if other != k)
    }


class BlobStore(Protocol):
    def exists_size(self, path: str) -> int | None: ...
    def upload(self, path: str, data: bytes) -> None: ...
    def list_sizes(self, prefix: str) -> dict[str, int]: ...
    def download(self, path: str) -> bytes: ...


class MemoryStore:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.uploads: dict[str, bytes] = {}
        self._fail = fail_upload
        # Test hook, called with (path, data) before each upload: lets a test
        # block, count or fail one upload without a blob account.
        self.on_upload = None

    def exists_size(self, path: str) -> int | None:
        return len(self.uploads[path]) if path in self.uploads else None

    def upload(self, path: str, data: bytes) -> None:
        if self.on_upload is not None:
            self.on_upload(path, data)
        if self._fail:
            raise OSError("simulated upload failure")
        self.uploads[path] = data

    def list_sizes(self, prefix: str) -> dict[str, int]:
        return {p: len(d) for p, d in self.uploads.items() if p.startswith(prefix)}

    def download(self, path: str) -> bytes:
        return self.uploads[path]


class DataLakeStore:
    """``fs``: filesystem client from gie.blobio.uploader(settings).
    ``container_client``: ocha_stratus.get_container_client(...) for listing."""

    def __init__(self, fs, container_client) -> None:
        self._fs = fs
        self._cc = container_client

    def exists_size(self, path: str) -> int | None:
        fc = self._fs.get_file_client(path)
        if not fc.exists():
            return None
        return fc.get_file_properties().size

    def upload(self, path: str, data: bytes) -> None:
        blobio.upload(self._fs, data, path)
        got = self._fs.get_file_client(path).get_file_properties().size
        if got != len(data):
            raise OSError(f"size mismatch after upload: blob={got} local={len(data)}")

    def list_sizes(self, prefix: str) -> dict[str, int]:
        sizes = {b.name: b.size for b in self._cc.list_blobs(name_starts_with=prefix)}
        return drop_directory_entries(sizes)

    def download(self, path: str) -> bytes:
        return self._cc.download_blob(path).readall()
