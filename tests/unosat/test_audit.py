import hashlib

import pandas as pd

from gie.unosat import audit, common, discovery, store
from tests.unosat.test_discovery import DS
from tests.unosat.test_silver import inventory_rows, ledger_rows


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


# --- S1: processing covers every SELECTED (sha256, layer) -------------------


def test_s1_passes_when_processing_covers_every_selected_layer():
    """A GDB dataset with a SHP sibling: only the GDB's own layer is
    *selected* for reading, so the sibling's layer needs no processing row."""
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1"},
        {"dataset_id": "d1", "sha256": "s1", "resource_name": "a_SHP.zip",
         "format": "SHP", "target_id": "t2"},
    )
    layers_df = inventory_rows(g1="gdb", s1="shp")
    proc_df = pd.DataFrame({"sha256": ["g1"], "layer": ["L_g1"]})
    ok, detail = audit.check_s1_processing_covers_selected(ledger, layers_df, proc_df)
    assert ok and "0 missing" in detail


def test_s1_fails_when_a_selected_layer_has_no_processing_row():
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1"},
    )
    layers_df = inventory_rows(g1="gdb")
    proc_df = pd.DataFrame({"sha256": pd.Series([], dtype="object"),
                             "layer": pd.Series([], dtype="object")})
    ok, detail = audit.check_s1_processing_covers_selected(ledger, layers_df, proc_df)
    assert not ok and "g1" in detail


# --- S2: every code with an ok layer has its partition -----------------------


def test_s2_passes_when_partitions_exist_for_ok_codes():
    proc_df = pd.DataFrame(
        {"table": ["observed_event", "coverage"], "status": ["ok", "ok"], "code": ["FL1", "FL1"]}
    )
    st = store.MemoryStore()
    st.upload(f"{common.SILVER}/observed_event/code=FL1/layer=a.parquet", b"x")
    st.upload(f"{common.SILVER}/coverage/code=FL1/layer=a.parquet", b"x")
    ok, _ = audit.check_s2_partitions_written(proc_df, st)
    assert ok


def test_s2_fails_when_a_code_with_an_ok_layer_has_no_partition():
    proc_df = pd.DataFrame({"table": ["observed_event"], "status": ["ok"], "code": ["FL1"]})
    ok, detail = audit.check_s2_partitions_written(proc_df, store.MemoryStore())
    assert not ok and "observed_event" in detail and "FL1" in detail


# --- S3: acquisition dates plausible ----------------------------------------


def _acq_rows(*rows: dict) -> pd.DataFrame:
    defaults = {
        "code": "FL20220424SSD",
        "acq_datetime": pd.Timestamp("2022-04-25"),
        "acq_window_start": pd.NaT,
        "acq_window_end": pd.NaT,
        "acq_precision": "date",
    }
    return pd.DataFrame([defaults | r for r in rows])


def test_s3_passes_for_a_plausible_date_near_the_event_code():
    ok, _ = audit.check_s3_acquisition_dates(_acq_rows({}), now=pd.Timestamp("2026-09-22"))
    assert ok


def test_s3_fails_for_a_date_far_from_the_event_code():
    rows = _acq_rows({"acq_datetime": pd.Timestamp("2010-01-01")})
    ok, detail = audit.check_s3_acquisition_dates(rows, now=pd.Timestamp("2026-09-22"))
    assert not ok and "FL20220424SSD" in detail


def test_s3_fails_for_a_year_outside_the_plausible_range():
    rows = _acq_rows({"code": "FL19990101SSD", "acq_datetime": pd.Timestamp("1999-01-01")})
    ok, detail = audit.check_s3_acquisition_dates(rows, now=pd.Timestamp("2026-09-22"))
    assert not ok


def test_s3_ignores_undated_rows():
    rows = _acq_rows({"acq_precision": "none", "acq_datetime": pd.NaT})
    ok, detail = audit.check_s3_acquisition_dates(rows, now=pd.Timestamp("2026-09-22"))
    assert ok and detail == "no dated rows"


def test_s3_passes_for_a_window_precision_row_spanning_several_months():
    """A window mid-point is what is checked against the event code's date and
    the plausible-year range, not either endpoint — pinned so a change to that
    midpoint logic is noticed."""
    rows = _acq_rows(
        {
            "acq_precision": "window",
            "acq_datetime": pd.NaT,
            "acq_window_start": pd.Timestamp("2022-03-01"),
            "acq_window_end": pd.Timestamp("2022-06-01"),
        }
    )
    ok, _ = audit.check_s3_acquisition_dates(rows, now=pd.Timestamp("2026-09-22"))
    assert ok


# --- S4: vocabularies --------------------------------------------------------


def test_s4_passes_within_vocabulary():
    frame = pd.DataFrame({"layer_kind": ["water", "flood", None]})
    ok, _ = audit.check_s4_vocabularies({"layer_kind": (frame, "layer_kind")})
    assert ok


def test_s4_fails_outside_vocabulary_and_names_the_codes():
    frame = pd.DataFrame({"layer_kind": ["water", "bogus_kind"], "code": ["FL1", "FL2"]})
    ok, detail = audit.check_s4_vocabularies({"layer_kind": (frame, "layer_kind")})
    assert not ok and "bogus_kind" in detail and "FL2" in detail


def test_s4_violation_reaches_stale_codes():
    """A code-bearing S4 violation lands its code in `stale_codes`'s
    reprocessing list — the bug this rule exists to prevent."""
    ledger, layers_df, proc_df, acq_rows, index = _empty_stale_inputs()
    frame = pd.DataFrame({"layer_kind": ["water", "bogus_kind"], "code": ["FL1", "FL2"]})
    stale = audit.stale_codes(
        ledger, layers_df, proc_df, store.MemoryStore(), acq_rows,
        {"layer_kind": (frame, "layer_kind")}, index, {},
    )
    assert {"FL2", "FL20190314MOZ"} <= stale


def test_s4_reports_a_violation_it_cannot_attribute():
    """A frame with no `code` column still fails the check (and says so
    plainly), it just cannot name which code to reprocess."""
    frame = pd.DataFrame({"layer_kind": ["bogus_kind"]})
    ok, detail = audit.check_s4_vocabularies({"layer_kind": (frame, "layer_kind")})
    assert not ok
    assert "bogus_kind" in detail
    assert "unattributable" in detail


# --- S5: unclassified share per code -----------------------------------------


def test_s5_passes_under_threshold():
    proc_df = pd.DataFrame({"code": ["FL1"] * 100, "status": ["ok"] * 97 + ["unclassified"] * 3})
    ok, _ = audit.check_s5_unclassified_share(proc_df)
    assert ok


def test_s5_fails_over_threshold():
    proc_df = pd.DataFrame({"code": ["FL1"] * 100, "status": ["ok"] * 90 + ["unclassified"] * 10})
    ok, detail = audit.check_s5_unclassified_share(proc_df)
    assert not ok and "FL1" in detail


# --- S6: shp/gdb sibling-check consistency -----------------------------------


def test_s6_passes_when_mismatch_and_status_agree():
    proc_df = pd.DataFrame(
        {
            "sha256": ["g1", "g2", "g3"],
            "layer": ["A", "B", "C"],
            "shp_gdb_mismatch": [["X"], None, None],
            "sibling_status": ["ok", "zip_unreadable", None],
        }
    )
    ok, _ = audit.check_s6_sibling_consistency(proc_df)
    assert ok


def test_s6_fails_when_ok_status_has_no_recorded_mismatch():
    proc_df = pd.DataFrame(
        {"sha256": ["g1"], "layer": ["A"], "shp_gdb_mismatch": [None], "sibling_status": ["ok"]}
    )
    ok, detail = audit.check_s6_sibling_consistency(proc_df)
    assert not ok and "g1" in detail


# --- S7: every built layer confirmed uploaded --------------------------------


def test_s7_passes_when_everything_confirmed_uploaded():
    proc_df = pd.DataFrame(
        {"table": ["observed_event"], "content_hash": ["h1"],
         "uploaded": pd.array([True], dtype="boolean")}
    )
    ok, _ = audit.check_s7_all_uploaded(proc_df)
    assert ok


def test_s7_fails_on_unconfirmed_upload():
    proc_df = pd.DataFrame(
        {"table": ["observed_event"], "content_hash": ["h1"],
         "uploaded": pd.array([False], dtype="boolean"), "sha256": ["g1"], "layer": ["A"]}
    )
    ok, detail = audit.check_s7_all_uploaded(proc_df)
    assert not ok and "g1" in detail


# --- surfaced, not failed -----------------------------------------------------


def test_silver_surfaces_counts_format_mismatch_and_multi_code():
    proc_df = pd.DataFrame(
        {"format_mismatch": [True, False, None], "codes_listed": [["A", "B"], ["A"], None]}
    )
    assert audit.silver_surfaces(proc_df) == {"format_mismatch": 1, "multi_code_contents": 1}


# --- G1: every gold row has geom_valid or valid_basis == "none" -------------


def test_g1_passes_when_every_row_has_a_mask_or_explicit_none():
    index = pd.DataFrame(
        {"code": ["FL1", "FL1"], "valid_basis": ["footprint", "none"],
         "valid_area_km2": [12.3, None]}
    )
    ok, _ = audit.check_g1_valid_mask_present(index)
    assert ok


def test_g1_fails_when_a_non_none_basis_has_no_mask():
    index = pd.DataFrame(
        {"code": ["FL1"], "valid_basis": ["footprint_minus_cloud"], "valid_area_km2": [None]}
    )
    ok, detail = audit.check_g1_valid_mask_present(index)
    assert not ok and "FL1" in detail


# --- G2: excluded-kind polygons never contribute, and are fully accounted for


def test_g2_passes_when_excluded_counts_match():
    observed_by_code = {
        "FL1": pd.DataFrame(
            {"layer_kind": ["aggregate_max", "flood", "water"], "acq_precision": ["date"] * 3}
        )
    }
    index = pd.DataFrame({"code": ["FL1", "FL1"], "excluded_aggregate_n": [1, 0]})
    ok, _ = audit.check_g2_excluded_accounting(observed_by_code, index)
    assert ok


def test_g2_fails_when_excluded_counts_disagree():
    observed_by_code = {
        "FL1": pd.DataFrame(
            {"layer_kind": ["aggregate_max", "aggregate_min", "flood"],
             "acq_precision": ["date"] * 3}
        )
    }
    index = pd.DataFrame({"code": ["FL1"], "excluded_aggregate_n": [1]})
    ok, detail = audit.check_g2_excluded_accounting(observed_by_code, index)
    assert not ok and "FL1" in detail


def test_g2_ignores_undated_excluded_polygons():
    """An excluded-kind layer with no date is dropped by `gold._prepare`
    before grouping, so it never reaches `excluded_aggregate_n` either."""
    observed_by_code = {
        "FL1": pd.DataFrame({"layer_kind": ["aggregate_max", "flood"], "acq_precision":
                              ["none", "date"]})
    }
    index = pd.DataFrame({"code": ["FL1"], "excluded_aggregate_n": [0]})
    ok, _ = audit.check_g2_excluded_accounting(observed_by_code, index)
    assert ok


def test_label_coverage_summary_reports_distributions():
    index = pd.DataFrame(
        {
            "sensor_class": ["sar", "sar"],
            "acq_precision": ["date", "window"],
            "valid_basis": ["none", "footprint"],
            "valid_match": [None, "product"],
            "countries": ["MOZ", "MOZ; ZWE"],
        }
    )
    out = audit.label_coverage_summary(index)
    assert out["n_label_sets"] == 2
    assert out["by_country"]["MOZ"] == 2
    assert out["by_sensor_class_acq_precision"] == {"sar/date": 1, "sar/window": 1}
    # how a mask that exists was matched: on the acquisition interval too, or
    # on source product and area alone
    assert out["by_valid_match"]["product"] == 1


def _empty_stale_inputs():
    """The `stale_codes` fixture shared by the tests below: one GDB unit with
    no processing row at all, so S1 always contributes `FL20190314MOZ` —
    used to check that another rule's contribution lands alongside it, not in
    place of it."""
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1"},
    )
    layers_df = inventory_rows(g1="gdb")
    proc_df = pd.DataFrame(
        {"sha256": pd.Series([], dtype="object"), "layer": pd.Series([], dtype="object"),
         "code": pd.Series([], dtype="object"), "status": pd.Series([], dtype="object"),
         "table": pd.Series([], dtype="object")}
    )
    acq_rows = pd.DataFrame(
        columns=["code", "acq_datetime", "acq_window_start", "acq_window_end", "acq_precision"]
    )
    index = pd.DataFrame(columns=["code", "valid_basis", "valid_area_km2", "excluded_aggregate_n"])
    return ledger, layers_df, proc_df, acq_rows, index


def test_stale_codes_collects_codes_from_any_failing_rule():
    ledger, layers_df, proc_df, acq_rows, index = _empty_stale_inputs()
    stale = audit.stale_codes(
        ledger, layers_df, proc_df, store.MemoryStore(), acq_rows, {}, index, {}
    )
    assert stale == {"FL20190314MOZ"}
