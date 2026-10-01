import hashlib

import pandas as pd

from gie.unosat import audit, common, discovery, store
from tests.unosat.test_discovery import DS


def _uploaded_ledger(data: bytes):
    led = discovery.resources_ledger([DS])
    sha = hashlib.sha256(data).hexdigest()
    led.loc[led.status == "pending", ["status", "sha256", "size_bytes"]] = [
        "uploaded",
        sha,
        len(data),
    ]
    return led, sha


def test_b1_fails_on_pending():
    led = discovery.resources_ledger([DS])
    ok, detail = audit.check_b1_no_pending(led)
    assert not ok and "3" in detail  # three pending rows in the fixture


def test_b2_passes_when_census_matches(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    st = store.MemoryStore()
    for name in led.loc[led.status == "uploaded", "resource_name"]:
        st.upload(common.blob_path(sha, name), good_zip)
    ok, _ = audit.check_b2_census(led, st)
    assert ok


def test_b2_fails_on_missing_or_extra_or_wrong_size(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    st = store.MemoryStore()
    names = list(led.loc[led.status == "uploaded", "resource_name"])
    st.upload(common.blob_path(sha, names[0]), good_zip[:-1])  # wrong size
    st.upload(common.blob_path("0" * 64, "stray.zip"), b"x")  # not in ledger
    ok, detail = audit.check_b2_census(led, st)
    assert not ok
    assert "missing" in detail and "extra" in detail and "size" in detail


def test_b3_requires_domain_status_for_every_uploaded_gdb(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    ok, detail = audit.check_b3_domains(led, pd.DataFrame(columns=["sha256", "status"]))
    assert not ok and sha[:8] in detail
    ok, _ = audit.check_b3_domains(led, pd.DataFrame({"sha256": [sha], "status": ["no_domains"]}))
    assert ok
