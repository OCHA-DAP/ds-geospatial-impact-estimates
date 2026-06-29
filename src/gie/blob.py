"""Robust blob upload helpers — stage small blocks instead of one large PUT.

The Azure SDK uploads any blob <= 64 MB (``max_single_put_size``) as a single
PUT: one long request. On a thin or flaky uplink that request stalls and dies,
while small per-block requests complete reliably (observed: a 27 MB single PUT
failed repeatedly; the same payload as 4 MB blocks uploaded in ~32s). These
helpers go through the ocha-stratus container client (team standard) and stage
4 MB blocks, each retried with a per-attempt stall timeout.
"""

from __future__ import annotations

import base64
import io
import threading
import time

import ocha_stratus as stratus
from azure.storage.blob import BlobBlock

BLOCK_SIZE = 4 * 1024 * 1024


def _stage(bc, block_id: str, chunk: bytes, tries: int = 6, timeout_s: int = 45) -> None:
    """Stage one block, retried with a per-attempt stall timeout."""
    for attempt in range(tries):
        result: dict = {}

        def _do(result=result):
            try:
                bc.stage_block(block_id=block_id, data=chunk, length=len(chunk))
                result["ok"] = True
            except Exception as e:  # noqa: BLE001 — network write, retry any failure
                result["err"] = e

        th = threading.Thread(target=_do, daemon=True)
        th.start()
        th.join(timeout_s)
        if result.get("ok"):
            return
        reason = "stalled" if th.is_alive() else str(result.get("err", ""))[:40]
        print(f"    block attempt {attempt + 1}/{tries} ({reason}); retrying", flush=True)
        time.sleep(3)
    raise RuntimeError(f"block stage failed after {tries} tries: {block_id}")


def upload_bytes_staged(
    data: bytes, blob: str, settings, stage: str = "dev", block_size: int = BLOCK_SIZE
) -> None:
    """Upload raw bytes via staged blocks through the stratus container client."""
    cc = stratus.get_container_client(container_name=settings.container, stage=stage, write=True)
    bc = cc.get_blob_client(blob)
    blocks = []
    for i, off in enumerate(range(0, len(data), block_size)):
        block_id = base64.b64encode(f"{i:06d}".encode()).decode()
        _stage(bc, block_id, data[off : off + block_size])
        blocks.append(BlobBlock(block_id=block_id))
    bc.commit_block_list(blocks)


def upload_parquet_staged(frame, blob: str, settings, stage: str = "dev") -> None:
    """Serialise a DataFrame or GeoDataFrame to Parquet (geometry/CRS preserved
    for GeoDataFrames) and upload it via staged blocks."""
    buf = io.BytesIO()
    frame.to_parquet(buf, compression="zstd", index=False)
    upload_bytes_staged(buf.getvalue(), blob, settings, stage=stage)
