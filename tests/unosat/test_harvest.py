import hashlib
import zipfile

import pytest
import requests

from gie.unosat import cache, common, harvest, store
from tests.unosat.conftest import FakeResponse, FakeSession, make_zip


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
