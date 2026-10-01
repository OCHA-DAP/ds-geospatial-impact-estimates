"""Reliable blob uploads for the HNS (ADLS Gen2) data lake.

The SDK's default single-PUT path sends anything under ``max_single_put_size``
(64 MiB) as ONE request — a single stream that crawls on a high-latency link and
trips the 60 s ``read_timeout`` on 20–40 MB files ("The write operation timed
out"). We upload via the DataLake (DFS) API — which also creates nested paths on
HNS (the Blob API 404s writing under a not-yet-existing directory) — forcing the
chunked, concurrent block path with a generous socket timeout, per Microsoft's
upload-tuning guidance
(https://learn.microsoft.com/azure/storage/blobs/storage-blobs-tune-upload-download-python).

Measured on this lake: single-PUT ~0.20 MB/s → chunked+concurrent ~1.55 MB/s (~8x),
and no timeout because each block's socket write is short.
"""

from __future__ import annotations

from azure.storage.filedatalake import DataLakeServiceClient

# 4 MiB blocks — DataLakeFileClient.upload_data defaults chunk_size to 100 MB, which
# would send a 20–40 MB file as one chunk (exactly the failure). Small blocks also
# make each socket write short and each per-block retry cheap.
_CHUNK_SIZE = 4 * 1024 * 1024
# Parallel blocks fill a high-latency pipe (the big throughput lever here).
_MAX_CONCURRENCY = 4
# Client socket timeout in seconds (SDK default 60) — the knob that governs the
# "write operation timed out" stall on a slow link.
_READ_TIMEOUT = 300


def uploader(settings, *, read_timeout: int = _READ_TIMEOUT) -> "any":
    """A tuned DataLake filesystem client. Build once; reuse across many uploads.

    ``read_timeout`` is the per-socket-operation timeout in seconds. The
    default suits one large sequential upload: waiting out a stalled socket is
    fine when there is nothing else to do. A caller pushing many small files
    concurrently should pass a much shorter one — there a stall blocks the
    whole pipeline, and failing onto a fresh connection is cheaper than
    waiting. UNOSAT silver passes 60: its median upload is 0.5 s, yet observed
    stalls ran to 470 s and accounted for half the wall time of a real run.
    """
    return DataLakeServiceClient(
        f"https://{settings.account_name}.dfs.core.windows.net",
        credential=settings.sas_token(write=True),
        read_timeout=read_timeout,
    ).get_file_system_client(settings.container)


def upload(fs, data: bytes, dest: str, *, overwrite: bool = True) -> None:
    """Upload ``data`` to the container-relative path ``dest``, reliably (chunked,
    concurrent). ``fs`` is a filesystem client from :func:`uploader`."""
    fs.get_file_client(dest).upload_data(
        data, overwrite=overwrite, chunk_size=_CHUNK_SIZE, max_concurrency=_MAX_CONCURRENCY
    )
