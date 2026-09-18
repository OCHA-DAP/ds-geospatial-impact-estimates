import hashlib
import json
import zipfile

import pandas as pd
import pytest
import requests

from gie.unosat import cache, common, discovery, harvest, store
from tests.unosat.conftest import FakeResponse, FakeSession, make_zip
from tests.unosat.test_discovery import DS


@pytest.fixture(autouse=True)
def _cache_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path / "cache"))


def _run(row, resp_or_exc, st=None, use_cache=True):
    session = FakeSession({row["url"]: resp_or_exc})
    st = st or store.MemoryStore()
    updates, members = harvest.process_target(
        row, session=session, store=st, limiter=common.HostLimiter(), use_cache=use_cache
    )
    return updates, members, st


def test_happy_path_uploads_hashes_inventories_and_caches(ledger_row, good_zip):
    updates, members, st = _run(ledger_row, FakeResponse(200, good_zip))
    sha = hashlib.sha256(good_zip).hexdigest()
    assert updates["status"] == "uploaded"
    assert updates["sha256"] == sha
    assert updates["size_bytes"] == len(good_zip)
    assert updates["n_members"] == 2 and len(members) == 2
    assert members[0]["sha256"] == sha and members[0]["target_id"] == ledger_row["target_id"]
    path = common.blob_path(sha, "FL20220424SSD_SHP.zip")
    assert st.exists_size(path) == len(good_zip)
    assert cache.cache_path(sha, "FL20220424SSD_SHP.zip").read_bytes() == good_zip
    assert updates["attempts"] == 1 and updates["http_status"] == 200


def test_attempts_tolerates_pd_na_on_first_attempt(ledger_row, good_zip):
    row = ledger_row.copy()
    row["attempts"] = pd.NA
    updates, _, _ = _run(row, FakeResponse(200, good_zip))
    assert updates["attempts"] == 1


def test_dedup_when_blob_already_holds_content(ledger_row, good_zip):
    sha = hashlib.sha256(good_zip).hexdigest()
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip)
    updates, members, st = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "uploaded_dedup"
    assert updates["sha256"] == sha
    assert len(st.uploads) == 1  # no second upload happened
    assert len(members) == 2  # inventory is still recorded for this target


def test_404_is_terminal_unavailable(ledger_row):
    updates, members, _ = _run(ledger_row, FakeResponse(404))
    assert updates["status"] == "unavailable_404"
    assert updates["http_status"] == 404
    assert members == [] and updates.get("sha256") is None


def test_200_but_not_a_zip_is_terminal_corrupt(ledger_row):
    updates, _, st = _run(ledger_row, FakeResponse(200, b"<html>not a zip</html>"))
    assert updates["status"] == "corrupt_upstream"
    assert updates["http_status"] == 200
    assert "BadZipFile" in updates["error"]
    assert st.uploads == {}


def test_network_error_is_retryable_failed_download(ledger_row):
    updates, _, _ = _run(ledger_row, requests.ConnectionError("boom"))
    assert updates["status"] == "failed_download"
    assert "ConnectionError" in updates["error"]


def test_upload_error_is_retryable_failed_upload(ledger_row, good_zip):
    st = store.MemoryStore(fail_upload=True)
    updates, _, _ = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "failed_upload"
    assert updates["sha256"] == hashlib.sha256(good_zip).hexdigest()  # hash kept for the retry


class _StoreThatLosesTheRace(store.MemoryStore):
    """Simulates a concurrent writer: the bytes land at ``path`` (a peer's
    upload won the race) but this call still raises, as a real client would
    on a conflicting concurrent write to the same path."""

    def upload(self, path: str, data: bytes) -> None:
        self.uploads[path] = data
        raise OSError("simulated conflicting concurrent write")


def test_lost_upload_race_to_identical_content_is_uploaded_dedup(ledger_row, good_zip):
    st = _StoreThatLosesTheRace()
    updates, members, _ = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "uploaded_dedup"
    assert updates["error"] is None
    assert updates["sha256"] == hashlib.sha256(good_zip).hexdigest()
    assert len(members) == 2


def test_no_cache_leaves_nothing_under_cache_root(ledger_row, good_zip, tmp_path):
    _run(ledger_row, FakeResponse(200, good_zip), use_cache=False)
    assert not (tmp_path / "cache" / "unosat").exists()


def test_inspect_zip_raises_on_corrupt_member(tmp_path):
    data = bytearray(make_zip({"a.txt": b"hello world" * 100}))
    data[-100:-90] = b"\x00" * 10  # damage the compressed member data (CRC mismatch on testzip)
    p = tmp_path / "bad.zip"
    p.write_bytes(bytes(data))
    with pytest.raises(zipfile.BadZipFile):
        harvest.inspect_zip(p)


def test_stream_download_hashes_while_streaming(tmp_path, good_zip):
    session = FakeSession({"https://unosat.org/a.zip": FakeResponse(200, good_zip)})
    res = harvest.stream_download(
        session, "https://unosat.org/a.zip", tmp_path / "a.zip", common.HostLimiter()
    )
    assert res.status_code == 200
    assert res.sha256 == hashlib.sha256(good_zip).hexdigest()
    assert res.size == len(good_zip) == (tmp_path / "a.zip").stat().st_size


def _ledger():
    return discovery.resources_ledger([DS]).set_index("target_id", drop=False)


def test_reconcile_marks_rows_whose_content_is_in_blob(good_zip):
    led = _ledger()
    sha = hashlib.sha256(good_zip).hexdigest()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["failed_upload", sha, len(good_zip)]
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip)
    led = harvest.reconcile_with_blob(led, st)
    assert led.loc[tid, "status"] == "uploaded"


def test_reconcile_demotes_uploaded_rows_whose_blob_is_missing(good_zip):
    led = _ledger()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["uploaded", "9" * 64, len(good_zip)]
    led = harvest.reconcile_with_blob(led, store.MemoryStore())
    assert led.loc[tid, "status"] == "pending"


def test_reconcile_demotes_size_mismatch(good_zip):
    led = _ledger()
    sha = hashlib.sha256(good_zip).hexdigest()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["uploaded", sha, len(good_zip)]
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip[:-5])  # truncated copy
    led = harvest.reconcile_with_blob(led, st)
    assert led.loc[tid, "status"] == "pending"


def test_reconcile_leaves_terminal_and_pending_rows_alone():
    led = _ledger()
    led.loc["r-gdb@2024-12-20T09:00:00", "status"] = "unavailable_404"
    led = harvest.reconcile_with_blob(led, store.MemoryStore())
    assert led.loc["r-gdb@2024-12-20T09:00:00", "status"] == "unavailable_404"
    assert led.loc["r-shp@2024-12-20T09:00:00", "status"] == "pending"


def test_journal_and_transfer_record_shape(tmp_path, ledger_row):
    rec = harvest.transfer_record(ledger_row, "dev", "uploaded", sha256="x" * 64, size_bytes=5)
    for key in ("ts", "outcome", "target_id", "source", "dataset", "provider", "licence",
                "origin_url", "host", "blob_path", "stage"):
        assert key in rec
    assert rec["source"] == "unosat" and rec["licence"] == "cc-by-sa"
    assert rec["blob_path"] == common.blob_path("x" * 64, "FL20220424SSD_SHP.zip")
    harvest.journal(tmp_path, rec)
    lines = (tmp_path / "transfers.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["outcome"] == "uploaded"


def test_checkpoint_writes_ledger_members_and_uploads_meta(tmp_path):
    led = _ledger()
    st = store.MemoryStore()
    (tmp_path / "datasets.parquet").write_bytes(b"")  # exists -> should be uploaded
    members = [{"target_id": "t", "sha256": "s", "event_code": "E", "member": "a.shp",
                "file_size": 1, "compress_size": 1}]
    left = harvest.checkpoint(tmp_path, led, members, st)
    assert left == []
    assert (tmp_path / "resources.parquet").exists()
    assert len(pd.read_parquet(tmp_path / "zip_contents.parquet")) == 1
    assert f"{common.META}/resources.parquet" in st.uploads
    assert f"{common.META}/zip_contents.parquet" in st.uploads
    # second checkpoint merges member rows per target_id instead of duplicating
    harvest.checkpoint(tmp_path, led, members, st)
    assert len(pd.read_parquet(tmp_path / "zip_contents.parquet")) == 1


def test_apply_updates_clears_stale_http_status_on_retryable_status(ledger_row):
    led = pd.DataFrame([ledger_row]).set_index("target_id", drop=False)
    tid = ledger_row["target_id"]
    led.loc[tid, "http_status"] = 500
    updates = {
        "status": "failed_download",
        "error": "ConnectionError",
        "attempts": 2,
        "attempted_at": "2024-12-20T09:00:00",
    }
    harvest.apply_updates(led, tid, updates)
    assert led.loc[tid, "status"] == "failed_download"
    assert led.loc[tid, "attempts"] == 2
    assert pd.isna(led.loc[tid, "http_status"])
