import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import requests

from gie.unosat import cache, common, discovery, harvest, store
from tests.unosat.conftest import FakeResponse, FakeSession, make_zip
from tests.unosat.test_discovery import DS, DS2

_CLI_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "unosat" / "harvest.py"


def _load_cli_module():
    """``pipelines/`` is not a package, so load the CLI script by path."""
    spec = importlib.util.spec_from_file_location("unosat_harvest_cli", _CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    assert updates["http_status"] is None  # no response, so nothing to record


def test_every_outcome_carries_state_keys_and_only_the_content_it_learned(ledger_row, good_zip):
    """State keys are always present — that is what lets ``apply_updates``
    clear stale values without special cases. A content key appears only when
    that branch actually got the bytes and learned it."""
    cases = [
        (FakeResponse(200, good_zip), None, "uploaded",
         {"sha256", "size_bytes", "n_members", "uploaded_at"}),
        (FakeResponse(404), None, "unavailable_404", set()),
        (FakeResponse(500), None, "failed_download", set()),
        (requests.ConnectionError("boom"), None, "failed_download", set()),
        (FakeResponse(200, b"not a zip"), None, "corrupt_upstream", {"size_bytes"}),
        (FakeResponse(200, good_zip), store.MemoryStore(fail_upload=True), "failed_upload",
         {"sha256", "size_bytes", "n_members"}),
    ]
    for resp_or_exc, st, expected_status, expected_content in cases:
        updates, _, _ = _run(ledger_row, resp_or_exc, st)
        assert updates["status"] == expected_status
        assert set(harvest.STATE_KEYS) <= set(updates), expected_status
        assert set(updates) & set(harvest.CONTENT_KEYS) == expected_content, expected_status


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


def test_lost_upload_race_keeps_zip_test_note_when_untested(ledger_row, good_zip, monkeypatch):
    """An uploaded_untested object (unsupported compression method) that loses
    the upload race must keep its zip_test note, not have it clobbered by the
    lost-race branch's own (unrelated) error."""
    monkeypatch.setattr(zipfile.ZipFile, "testzip", _raise_unsupported_compression)
    st = _StoreThatLosesTheRace()
    updates, _, _ = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "uploaded_dedup"
    assert updates["error"] == "zip_test: unsupported compression method"


class _StoreWithBuggyUpload(store.MemoryStore):
    """A KeyError here is a bug in our own code, not an upstream/store failure
    — it must propagate, not be recorded as failed_upload."""

    def upload(self, path: str, data: bytes) -> None:
        raise KeyError("bug")


def test_upload_bug_propagates(ledger_row, good_zip):
    st = _StoreWithBuggyUpload()
    with pytest.raises(KeyError, match="bug"):
        _run(ledger_row, FakeResponse(200, good_zip), st)


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


def _raise_unsupported_compression(self):
    raise NotImplementedError("That compression method is not supported")


def test_inspect_zip_reports_untested_for_unsupported_compression(tmp_path, good_zip, monkeypatch):
    p = tmp_path / "untested.zip"
    p.write_bytes(good_zip)
    monkeypatch.setattr(zipfile.ZipFile, "testzip", _raise_unsupported_compression)
    infos, tested = harvest.inspect_zip(p)
    assert tested is False
    assert len(infos) == 2


def test_good_zip_is_tested(good_zip, tmp_path):
    p = tmp_path / "good.zip"
    p.write_bytes(good_zip)
    infos, tested = harvest.inspect_zip(p)
    assert tested is True
    assert len(infos) == 2


def test_unsupported_compression_is_uploaded_untested(ledger_row, good_zip, monkeypatch):
    monkeypatch.setattr(zipfile.ZipFile, "testzip", _raise_unsupported_compression)
    updates, members, st = _run(ledger_row, FakeResponse(200, good_zip))
    assert updates["status"] == "uploaded_untested"
    assert updates["error"] == "zip_test: unsupported compression method"
    assert updates["sha256"] == hashlib.sha256(good_zip).hexdigest()
    assert updates["n_members"] == 2 and len(members) == 2
    path = common.blob_path(updates["sha256"], "FL20220424SSD_SHP.zip")
    assert st.exists_size(path) == len(good_zip)


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
    """The network-exception branch has no HTTP status, so its outcome carries
    http_status=None; applying it must clear the 500 an earlier attempt left."""
    led = pd.DataFrame([ledger_row]).set_index("target_id", drop=False)
    tid = ledger_row["target_id"]
    led.loc[tid, "http_status"] = 500
    updates = {
        "status": "failed_download",
        "http_status": None,
        "error": "ConnectionError",
        "attempts": 2,
        "attempted_at": "2024-12-20T09:00:00",
    }
    harvest.apply_updates(led, tid, updates)
    assert led.loc[tid, "status"] == "failed_download"
    assert led.loc[tid, "attempts"] == 2
    assert pd.isna(led.loc[tid, "http_status"])


def test_failed_retry_keeps_previously_learned_content_facts(ledger_row):
    """A retry that never reaches the bytes must not erase what an earlier
    attempt learned: the sha256/size/members stay, so reconcile_with_blob can
    still find the object in the census and heal the row."""
    led = pd.DataFrame([ledger_row]).set_index("target_id", drop=False)
    tid = ledger_row["target_id"]
    led.loc[tid, ["status", "sha256", "size_bytes", "n_members", "http_status"]] = [
        "failed_upload", "f" * 64, 10, 2, 500,
    ]

    updates, _, _ = _run(led.loc[tid], requests.ConnectionError("boom"))
    harvest.apply_updates(led, tid, updates)

    assert led.loc[tid, "status"] == "failed_download"
    assert pd.isna(led.loc[tid, "http_status"])  # the stale 500 is cleared
    assert led.loc[tid, "sha256"] == "f" * 64
    assert led.loc[tid, "size_bytes"] == 10
    assert led.loc[tid, "n_members"] == 2


def _ledger2():
    return discovery.resources_ledger([DS, DS2]).set_index("target_id", drop=False)


_TID_SHP = "r-shp@2024-12-20T09:00:00"  # DS: FL20220424SSD_SHP.zip
_TID_SHP2 = "r-shp-2@2024-12-22T09:00:00"  # DS2: same URL as _TID_SHP
_TID_OTHER = "r-other@2024-12-22T09:00:00"  # DS2: a different URL


def test_settle_url_siblings_marks_sibling_uploaded_dedup_with_same_sha():
    led = _ledger2()
    sha = "a" * 64
    led.loc[_TID_SHP, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", sha, 56726504, 2,
    ]
    settled = dict(harvest.settle_url_siblings(led))
    assert _TID_SHP2 in settled
    upd = settled[_TID_SHP2]
    assert upd["status"] == "uploaded_dedup"
    assert upd["sha256"] == sha
    assert upd["size_bytes"] == 56726504
    assert upd["n_members"] == 2
    assert upd["http_status"] == 200
    assert upd["error"] is None
    assert "uploaded_at" in upd


def test_settle_url_siblings_ignores_row_with_different_url():
    led = _ledger2()
    led.loc[_TID_SHP, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", "a" * 64, 56726504, 2,
    ]
    settled = dict(harvest.settle_url_siblings(led))
    assert _TID_OTHER not in settled


def test_settle_url_siblings_ignores_hdx_size_mismatch():
    led = _ledger2()
    led.loc[_TID_SHP, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", "a" * 64, 56726504, 2,
    ]
    led.loc[_TID_SHP2, "hdx_size"] = 999  # differs from the representative's hdx_size
    settled = dict(harvest.settle_url_siblings(led))
    assert _TID_SHP2 not in settled


def test_settle_url_siblings_does_not_settle_unknown_size_from_known_size():
    """An undeclared hdx_size is not a wildcard: nothing says the pending row's
    bytes are the uploaded row's bytes, so it is downloaded, not settled."""
    led = _ledger2()
    led.loc[_TID_SHP, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", "a" * 64, 56726504, 2,
    ]
    led.loc[_TID_SHP2, "hdx_size"] = pd.NA
    settled = dict(harvest.settle_url_siblings(led))
    assert _TID_SHP2 not in settled


def test_settle_url_siblings_settles_unknown_size_from_unknown_size():
    led = _ledger2()
    led.loc[[_TID_SHP, _TID_SHP2], "hdx_size"] = pd.NA
    led.loc[_TID_SHP, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", "a" * 64, 56726504, 2,
    ]
    settled = dict(harvest.settle_url_siblings(led))
    assert settled[_TID_SHP2]["sha256"] == "a" * 64


def test_representatives_groups_shared_url_into_one_rep_and_one_sibling():
    led = _ledger2()
    todo = led[led["status"] == "pending"]
    reps, siblings = harvest.representatives(todo)
    rep_ids = set(reps["target_id"])
    assert (_TID_SHP in rep_ids) != (_TID_SHP2 in rep_ids)  # exactly one is the rep
    rep_id = _TID_SHP if _TID_SHP in rep_ids else _TID_SHP2
    other = _TID_SHP2 if rep_id == _TID_SHP else _TID_SHP
    assert siblings[rep_id] == [other]


def test_representatives_unique_url_has_no_siblings():
    led = _ledger2()
    todo = led[led["status"] == "pending"]
    reps, siblings = harvest.representatives(todo)
    assert _TID_OTHER in reps["target_id"].values  # r-other: unique URL
    assert siblings[_TID_OTHER] == []


def test_representatives_splits_same_url_on_hdx_size_mismatch():
    """A missing hdx_size must not be treated as a wildcard that merges with a
    row that declares a known size: each is its own representative."""
    led = _ledger2()
    led.loc[_TID_SHP2, "hdx_size"] = pd.NA
    todo = led[led["status"] == "pending"]
    reps, siblings = harvest.representatives(todo)
    rep_ids = set(reps["target_id"])
    assert _TID_SHP in rep_ids and _TID_SHP2 in rep_ids  # both are representatives now
    assert siblings[_TID_SHP] == []
    assert siblings[_TID_SHP2] == []


def test_sibling_updates_for_success_outcome_is_uploaded_dedup_without_attempts():
    updates = {
        "attempts": 1, "attempted_at": "2024-01-01T00:00:00",
        "status": "uploaded", "http_status": 200, "error": None,
        "sha256": "a" * 64, "size_bytes": 100, "n_members": 2,
        "uploaded_at": "2024-01-01T00:00:01",
    }
    members = [
        {"target_id": "rep-1", "sha256": "a" * 64, "event_code": "FL20220424SSD",
         "member": "a.shp", "file_size": 1, "compress_size": 1},
    ]
    sib_updates, sib_members = harvest.sibling_updates(updates, members, "sib-1")
    assert sib_updates["status"] == "uploaded_dedup"
    assert sib_updates["sha256"] == "a" * 64
    assert sib_updates["size_bytes"] == 100
    assert sib_updates["n_members"] == 2
    assert "attempts" not in sib_updates
    assert "attempted_at" not in sib_updates
    assert sib_members == [{**members[0], "target_id": "sib-1"}]


def test_sibling_updates_for_terminal_outcome_is_identical_without_attempts():
    updates = {
        "attempts": 1, "attempted_at": "2024-01-01T00:00:00",
        "status": "unavailable_404", "http_status": 404, "error": "HTTP 404",
    }
    sib_updates, sib_members = harvest.sibling_updates(updates, [], "sib-1")
    assert sib_updates["status"] == "unavailable_404"
    assert sib_updates["http_status"] == 404
    assert sib_updates["error"] == "HTTP 404"
    assert "attempts" not in sib_updates
    assert "attempted_at" not in sib_updates
    assert sib_members == []


def _journal_lines(work_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (work_dir / "transfers.jsonl").read_text().splitlines()]


def test_record_outcome_updates_the_ledger_and_writes_one_journal_line(tmp_path):
    led = _ledger2()
    updates = harvest._outcome(
        status="uploaded", http_status=200, sha256="a" * 64, size_bytes=100, n_members=2,
        uploaded_at="2024-01-01T00:00:01", attempts=1, attempted_at="2024-01-01T00:00:00",
    )
    members = [{"target_id": _TID_SHP, "sha256": "a" * 64, "event_code": "FL20220424SSD",
                "member": "a.shp", "file_size": 1, "compress_size": 1}]

    returned = harvest.record_outcome(
        led, tmp_path, "dev", _TID_SHP, updates, members, via="url_sibling"
    )

    assert returned == members  # pass-through, so callers can accumulate in one expression
    assert led.loc[_TID_SHP, "status"] == "uploaded"
    assert led.loc[_TID_SHP, "sha256"] == "a" * 64
    lines = _journal_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["outcome"] == "uploaded"
    assert lines[0]["target_id"] == _TID_SHP
    assert lines[0]["via"] == "url_sibling"
    assert lines[0]["blob_path"] == common.blob_path("a" * 64, "FL20220424SSD_SHP.zip")


def test_propagate_to_siblings_records_every_sibling_once(tmp_path):
    led = _ledger2()
    updates = harvest._outcome(
        status="uploaded", http_status=200, sha256="a" * 64, size_bytes=100, n_members=2,
        uploaded_at="2024-01-01T00:00:01", attempts=1, attempted_at="2024-01-01T00:00:00",
    )
    members = [{"target_id": _TID_SHP, "sha256": "a" * 64, "event_code": "FL20220424SSD",
                "member": "a.shp", "file_size": 1, "compress_size": 1}]
    sibling_ids = [_TID_SHP2, _TID_OTHER]

    out = harvest.propagate_to_siblings(led, tmp_path, "dev", updates, members, sibling_ids)

    assert [m["target_id"] for m in out] == sibling_ids  # N siblings x N member rows
    assert list(led.loc[sibling_ids, "status"]) == ["uploaded_dedup"] * 2
    assert list(led.loc[sibling_ids, "sha256"]) == ["a" * 64] * 2
    assert list(led.loc[sibling_ids, "attempts"]) == [0, 0]  # no attempt was made for a sibling
    lines = _journal_lines(tmp_path)
    assert [x["target_id"] for x in lines] == sibling_ids
    assert {x["outcome"] for x in lines} == {"uploaded_dedup"}
    assert {x["via"] for x in lines} == {"url_sibling"}


def test_outcome_marker_flags_failures_only():
    assert harvest.outcome_marker({"status": "uploaded"}) == "uploaded"
    assert harvest.outcome_marker({"status": "uploaded_dedup"}) == "uploaded_dedup"
    assert (
        harvest.outcome_marker({"status": "failed_download", "error": "HTTP 500"})
        == "** failed_download: HTTP 500"
    )


def test_cli_dry_run_is_side_effect_free_and_reports_settled_count(tmp_path, monkeypatch, capsys):
    """--dry-run must not journal or persist settle_url_siblings' results: the
    representative row is already 'uploaded', its DS2 sibling shares the URL
    and hdx_size, so settle_url_siblings would settle exactly it — but a dry
    run only reports the count, it doesn't apply or journal it."""
    cli = _load_cli_module()

    led = discovery.resources_ledger([DS, DS2])
    sha = "a" * 64
    rep_mask = led["target_id"] == "r-shp@2024-12-20T09:00:00"
    led.loc[rep_mask, ["status", "sha256", "size_bytes", "n_members"]] = [
        "uploaded", sha, 56726504, 2,
    ]
    led = common.coerce_ledger_dtypes(led)
    led.to_parquet(tmp_path / "resources.parquet")

    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), b"x" * 56726504)
    _patch_cli_blob(cli, monkeypatch, st)

    cli.main(["--dry-run", "--work-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert "1 settled" in out
    assert not (tmp_path / "transfers.jsonl").exists()


class _NoMetaContainerClient:
    """No blob _meta/ files exist yet; bootstrap must restore nothing."""

    def download_blob(self, path):
        from azure.core.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError(f"{path} not found")


def _patch_cli_blob(cli, monkeypatch, st):
    # meta.bootstrap is what opens the container client for every unosat CLI.
    monkeypatch.setattr(
        cli.meta.stratus, "get_container_client", lambda **kw: _NoMetaContainerClient()
    )
    monkeypatch.setattr(cli.blobio, "uploader", lambda settings: object())
    monkeypatch.setattr(cli, "DataLakeStore", lambda fs, cc: st)


def test_cli_run_records_the_representative_then_each_sibling(
    tmp_path, monkeypatch, capsys, good_zip
):
    """The two DS/DS2 rows share a URL and declared size: one is downloaded,
    the other is settled from it. Both get a numbered progress line and a
    journal entry, and the sibling's names the representative."""
    cli = _load_cli_module()

    led = discovery.resources_ledger([DS, DS2])
    led = common.coerce_ledger_dtypes(led[led["target_id"].isin([_TID_SHP, _TID_SHP2])])
    led.to_parquet(tmp_path / "resources.parquet")

    st = store.MemoryStore()
    _patch_cli_blob(cli, monkeypatch, st)
    url = "https://unosat.org/static/x/FL20220424SSD_SHP.zip"
    monkeypatch.setattr(
        cli.common, "make_session", lambda: FakeSession({url: FakeResponse(200, good_zip)})
    )

    cli.main(["--work-dir", str(tmp_path), "--workers", "1", "--sleep", "0"])

    out = capsys.readouterr().out
    assert "[1/2]" in out and "[2/2]" in out
    assert "(via " in out  # the sibling line names the representative it came from
    lines = _journal_lines(tmp_path)
    assert sorted(x["target_id"] for x in lines) == sorted([_TID_SHP, _TID_SHP2])
    assert {x["outcome"] for x in lines} == {"uploaded", "uploaded_dedup"}
    assert [x["via"] for x in lines] == [None, "url_sibling"]  # representative first
    final = pd.read_parquet(tmp_path / "resources.parquet").set_index("target_id")
    assert set(final["status"]) == {"uploaded", "uploaded_dedup"}
    assert len(set(final["sha256"])) == 1  # both rows point at the one uploaded object
    assert len(pd.read_parquet(tmp_path / "zip_contents.parquet")) == 4  # 2 members x 2 rows
