import threading
import time

from gie.unosat import common


def test_parse_event_code_from_resource_name():
    assert common.parse_event_code("FL20220424SSD_SHP.zip") == {
        "event_code": "FL20220424SSD",
        "hazard_prefix": "FL",
        "iso3": "SSD",
    }
    assert common.parse_event_code("TC20220221MDG_gdb.zip")["hazard_prefix"] == "TC"


def test_parse_event_code_rejects_non_matching_names():
    assert common.parse_event_code("UNOSAT_PopulationExposure_20260826_Nepal.xlsx") is None
    assert common.parse_event_code("") is None


def test_scope_for_prefix():
    assert common.scope_for("FL") == "flood"
    assert common.scope_for("TC") == "flood"
    assert common.scope_for("EQ") == "other"
    assert common.scope_for(None) == "unknown"


def test_blob_path_is_content_addressed():
    sha = "a" * 64
    assert common.blob_path(sha, "FL20220424SSD_SHP.zip") == (
        "unosat/bronze/blob=" + sha + "/FL20220424SSD_SHP.zip"
    )


def test_status_vocabularies_are_disjoint_and_complete():
    all_statuses = {
        "pending", "excluded_kmz", "uploaded", "uploaded_dedup",
        "failed_download", "failed_upload", "unavailable_404", "corrupt_upstream",
    }
    assert all_statuses >= common.TERMINAL_STATUSES
    assert all_statuses >= common.RETRYABLE_STATUSES
    assert not (common.TERMINAL_STATUSES & common.RETRYABLE_STATUSES)
    assert {"unavailable_404", "corrupt_upstream"} == common.TERMINAL_STATUSES
    assert {"failed_download", "failed_upload"} == common.RETRYABLE_STATUSES


def test_host_limiter_caps_concurrency_per_host():
    lim = common.HostLimiter(max_per_host=2)
    active = {"n": 0, "peak": 0}
    lock = threading.Lock()

    def work():
        with lim.acquire("https://unosat.org/x.zip"):
            with lock:
                active["n"] += 1
                active["peak"] = max(active["peak"], active["n"])
            time.sleep(0.05)
            with lock:
                active["n"] -= 1

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert active["peak"] == 2


def test_host_limiter_is_per_host():
    lim = common.HostLimiter(max_per_host=1)
    with lim.acquire("https://unosat.org/a.zip"), \
            lim.acquire("https://unosat-maps.web.cern.ch/b.zip"):
        # a different host is not blocked by the first host's slot
        pass


def test_session_has_user_agent_and_retries():
    s = common.make_session()
    assert s.headers["User-Agent"].startswith("OCHA-CHD-DS unosat-archive")
    adapter = s.get_adapter("https://unosat.org/")
    assert adapter.max_retries.total == 4
    assert 429 in adapter.max_retries.status_forcelist
