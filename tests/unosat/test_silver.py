import importlib.util
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon

from gie.unosat import common, domains, grammar, layers, silver
from gie.unosat.store import MemoryStore

_CLI_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "unosat" / "silver.py"

SQUARES = [
    Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
    Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
]

# (Water_Class code -> resolved text) as domains.parquet carries it for one
# (sha256, layer, field) triple; the silver builder is handed one such map
# per field name.
WATER_CLASS_DOMAIN = {
    "Water_Class": {"1": "Flood Water", "5": "Permanent Water", "9": "Aquaculture"}
}

FLOOD_LAYER = "ST1_20190330_FloodExtent_Beira_MOZ"
COVERAGE_LAYER = "ST1_20190330_AnalysisExtent_Beira_MOZ"
SKIP_LAYER = "ST1_20190330_DamagedStructures_Beira_MOZ"
UNDATED_FLOOD_LAYER = "ST1_FloodExtent_Beira_MOZ"


def make_gdf(attrs: dict, *, n: int = 2, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(attrs, geometry=SQUARES[:n], crs=crs)


def build(layer: str, gdf, **kwargs):
    """`build_layer` with the fixed arguments the tests never vary."""
    params = {
        "source": "gdb",
        "sha256": "a" * 64,
        "target_ids": ["res-1@2024-01-01T00:00:00"],
        "domain_lookup": WATER_CLASS_DOMAIN,
    }
    params.update(kwargs)
    return silver.build_layer("FL20190314MOZ", "resource_name", grammar.parse(layer), gdf, **params)


def test_observed_rows_resolve_kinds_from_the_domain():
    gdf = make_gdf({"Water_Class": [1, 5], "Sensor_ID": [None, None]})
    rows, table, record = build(FLOOD_LAYER, gdf)
    assert table == "observed_event"
    assert record["status"] == "ok"
    assert list(rows["layer_kind"]) == ["flood", "water_pre"]
    assert list(rows["class_text"]) == ["Flood Water", "Permanent Water"]
    assert list(rows["class_method"]) == ["domain", "domain"]
    # the polygon class wins over the layer name and the disagreement is flagged
    assert list(rows["class_conflict"]) == [False, True]
    assert list(rows.columns) == silver.OBSERVED_COLUMNS


def test_observed_rows_carry_the_acquisition_and_provenance_columns():
    gdf = make_gdf({"Water_Class": [1, 1]})
    rows, _, record = build(FLOOD_LAYER, gdf)
    assert list(rows["acq_datetime"]) == [datetime(2019, 3, 30)] * 2
    assert list(rows["acq_precision"]) == ["date", "date"]
    assert list(rows["acq_method"]) == ["filename", "filename"]
    assert not rows["acq_conflict"].any()
    assert list(rows["sensor"]) == ["Sentinel-1", "Sentinel-1"]
    assert list(rows["area_label"]) == ["Beira_MOZ", "Beira_MOZ"]
    assert list(rows["geometry_source"]) == ["gdb", "gdb"]
    assert list(rows["source_crs"]) == ["EPSG:4326", "EPSG:4326"]
    assert (rows["content_hash"] == record["content_hash"]).all()
    assert list(rows["target_ids"].iloc[0]) == ["res-1@2024-01-01T00:00:00"]
    assert json.loads(rows["attrs_json"].iloc[0])["Water_Class"] == 1


def test_unresolvable_polygon_class_falls_back_to_the_layer_name():
    # code 7 is not in the domain: resolve_class yields no kind, so the layer
    # name supplies it and class_method records that fallback.
    gdf = make_gdf({"Water_Class": [7, 7]})
    rows, _, _ = build(FLOOD_LAYER, gdf)
    assert list(rows["layer_kind"]) == ["flood", "flood"]
    assert list(rows["class_method"]) == ["layer_name", "layer_name"]
    assert list(rows["class_text"]) == [None, None]
    assert not rows["class_conflict"].any()


def test_unfilled_records_fall_back_to_the_layer_name():
    gdf = make_gdf({"Water_Class": [0, 0], "Sensor_ID": [0, 0], "Confidence_ID": [0, 0]})
    rows, _, _ = build(FLOOD_LAYER, gdf)
    assert list(rows["layer_kind"]) == ["flood", "flood"]
    assert list(rows["class_method"]) == ["layer_name", "layer_name"]


def test_shp_text_class_and_decoded_column():
    gdf = make_gdf(
        {"Water_Clas": [1, 1], "d_Water_Cl": ["Flood Water", "Satellite Detected Water"]}
    )
    rows, _, _ = build(FLOOD_LAYER, gdf, source="shp", domain_lookup=None)
    assert list(rows["layer_kind"]) == ["flood", "water"]
    assert list(rows["class_method"]) == ["decoded_column", "decoded_column"]
    assert list(rows["geometry_source"]) == ["shp", "shp"]


def test_coverage_layer_yields_coverage_rows_with_a_role():
    gdf = make_gdf({"SensorDate": [pd.Timestamp("2019-03-30")] * 2})
    rows, table, record = build(COVERAGE_LAYER, gdf)
    assert table == "coverage"
    assert record["status"] == "ok"
    assert list(rows["role"]) == ["footprint", "footprint"]
    assert list(rows.columns) == silver.COVERAGE_COLUMNS
    assert list(rows["acq_method"]) == ["attribute", "attribute"]


def test_skip_layer_is_recorded_and_produces_no_rows():
    rows, table, record = build(SKIP_LAYER, make_gdf({"Water_Class": [1, 1]}))
    assert rows is None and table is None
    assert record["status"] == "skipped_non_water"
    assert record["n_polygons"] == 2


def test_unclassified_layer_is_recorded_and_produces_no_rows():
    rows, table, record = build("ST1_20190330_Mystery_Zone", make_gdf({"a": [1, 1]}))
    assert rows is None and table is None
    assert record["status"] == "unclassified"


def test_non_polygon_layer_is_skipped():
    gdf = gpd.GeoDataFrame(
        {"Water_Class": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:4326"
    )
    rows, table, record = build(FLOOD_LAYER, gdf)
    assert rows is None and table is None
    assert record["status"] == "skipped_non_water"


def test_two_sensor_dates_become_two_acquisition_groups():
    gdf = make_gdf(
        {
            "Water_Class": [1, 1],
            "Sensor_Date": [pd.Timestamp("2019-03-30"), pd.Timestamp("2019-04-02")],
        }
    )
    rows, _, record = build(UNDATED_FLOOD_LAYER, gdf)
    assert sorted(rows["acq_datetime"]) == [datetime(2019, 3, 30), datetime(2019, 4, 2)]
    assert list(rows["acq_method"]) == ["attribute", "attribute"]
    assert record["status"] == "ok"


def test_null_sensor_dates_form_their_own_group():
    gdf = make_gdf(
        {"Water_Class": [1, 1], "Sensor_Date": [pd.Timestamp("2019-03-30"), pd.NaT]}
    )
    rows, _, _ = build(UNDATED_FLOOD_LAYER, gdf)
    # the acq_* columns are pinned to datetime64 for schema stability across
    # files, so the dateless group reads back as NaT, not None
    assert rows["acq_datetime"].iloc[0] == datetime(2019, 3, 30)
    assert pd.isna(rows["acq_datetime"].iloc[1])
    assert list(rows["acq_precision"]) == ["date", "none"]


def test_layer_with_no_date_anywhere_is_recorded_no_date_but_keeps_its_rows():
    rows, table, record = build(UNDATED_FLOOD_LAYER, make_gdf({"Water_Class": [1, 1]}))
    assert record["status"] == "no_date"
    assert table == "observed_event"
    # kept in silver, excluded from gold by acq_precision (spec §3)
    assert len(rows) == 2
    assert list(rows["acq_precision"]) == ["none", "none"]


def test_empty_layer_is_ok_with_zero_rows():
    gdf = gpd.GeoDataFrame({"Water_Class": []}, geometry=[], crs="EPSG:4326")
    rows, table, record = build(FLOOD_LAYER, gdf)
    assert record["status"] == "ok"
    assert record["n_polygons"] == 0
    assert table == "observed_event"
    assert len(rows) == 0
    assert list(rows.columns) == silver.OBSERVED_COLUMNS


def test_processing_record_counts_polygons_by_kind():
    gdf = make_gdf({"Water_Class": [1, 5]})
    _, _, record = build(FLOOD_LAYER, gdf)
    assert json.loads(record["kind_counts_json"]) == {"flood": 1, "water_pre": 1}
    assert list(record["target_ids"]) == ["res-1@2024-01-01T00:00:00"]
    assert record["layer"] == FLOOD_LAYER


def test_content_hash_is_equal_across_two_identical_inputs():
    a = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 5]}))[2]
    b = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 5]}))[2]
    assert a["content_hash"] == b["content_hash"]
    assert len(a["content_hash"]) == 64


def test_reprojected_layer_records_its_source_crs():
    gdf = gpd.GeoDataFrame(
        {"Water_Class": [1]},
        geometry=[Polygon([(500000, 0), (500100, 0), (500100, 100), (500000, 100)])],
        crs="EPSG:32636",
    )
    rows, _, record = build(FLOOD_LAYER, gdf)
    assert record["source_crs"] == "EPSG:32636"
    assert rows.crs.to_epsg() == 4326
    assert list(rows["source_crs"]) == ["EPSG:32636"]


def test_silver_layer_path_partitions_by_code_content_and_layer_name():
    path = silver.silver_layer_path("observed_event", "FL20190314MOZ", "b" * 64, FLOOD_LAYER)
    key = silver.layer_file_key("b" * 64, FLOOD_LAYER)
    assert path == f"unosat/silver/observed_event/code=FL20190314MOZ/layer={key}.parquet"
    assert key.startswith("b" * 64 + "-") and len(key) == 64 + 1 + 8


def test_identical_content_under_two_layer_names_gets_two_files():
    """Two acquisition dates over one analysis footprint are two layers;
    keying the file on content alone silently dropped the second."""
    store = MemoryStore()
    keys = []
    for layer in (COVERAGE_LAYER, "ST1_20190402_AnalysisExtent_Beira_MOZ"):
        rows, table, record = build(layer, make_gdf({"a": [1, 2]}))
        path = silver.silver_layer_path(table, "FL20190314MOZ", record["content_hash"], layer)
        keys.append(path.split("layer=")[1])
        silver.write_layer(store, path, rows)

    assert len(store.uploads) == 2
    # identical content, different name: the hash half matches, the name half does not
    assert keys[0][:64] == keys[1][:64]
    assert keys[0] != keys[1]


def test_write_layer_is_idempotent_for_identical_content():
    store = MemoryStore()
    rows, table, record = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 5]}))
    path = silver.silver_layer_path(table, "FL20190314MOZ", record["content_hash"], FLOOD_LAYER)
    assert store.exists_size(path) is None
    silver.write_layer(store, path, rows)
    assert store.exists_size(path) is not None

    # the same layer re-shipped in another zip hashes the same, so it lands on
    # the same path and the exists-check skips the second write entirely
    rows2, table2, record2 = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 5]}))
    path2 = silver.silver_layer_path(
        table2, "FL20190314MOZ", record2["content_hash"], FLOOD_LAYER
    )
    assert path2 == path
    assert store.exists_size(path2) is not None
    assert len(store.uploads) == 1

    back = gpd.read_parquet(io.BytesIO(store.uploads[path]))
    assert list(back.columns) == silver.OBSERVED_COLUMNS
    assert list(back["layer_kind"]) == ["flood", "water_pre"]


def test_write_layer_round_trips_an_empty_layer():
    store = MemoryStore()
    gdf = gpd.GeoDataFrame({"Water_Class": []}, geometry=[], crs="EPSG:4326")
    rows, table, record = build(FLOOD_LAYER, gdf)
    path = silver.silver_layer_path(table, "FL20190314MOZ", record["content_hash"], FLOOD_LAYER)
    silver.write_layer(store, path, rows)
    back = gpd.read_parquet(io.BytesIO(store.uploads[path]))
    assert len(back) == 0
    assert list(back.columns) == silver.OBSERVED_COLUMNS


def test_source_rows_are_distinct_per_sensor_and_acquisition():
    gdf = make_gdf(
        {
            "Water_Class": [1, 1],
            "Sensor_Date": [pd.Timestamp("2019-03-30"), pd.Timestamp("2019-04-02")],
        }
    )
    ln = grammar.parse(UNDATED_FLOOD_LAYER)
    groups = silver.layer_acquisitions(ln, gdf)
    rows = silver.source_rows("FL20190314MOZ", ln, groups, domain_lookup=None)
    assert len(rows) == 2
    assert {r["sensor"] for r in rows} == {"Sentinel-1"}
    assert {r["sensor_method"] for r in rows} == {"filename"}
    assert sorted(r["acq_datetime"] for r in rows) == [
        datetime(2019, 3, 30),
        datetime(2019, 4, 2),
    ]
    assert list(silver.sources_frame(rows).columns) == silver.SOURCES_COLUMNS


SENSORLESS_FLOOD_LAYER = "Beira_20190330_FloodExtent_MOZ"
SENSOR_ID_DOMAIN = {"Water_Class": {"1": "Flood Water"}, "Sensor_ID": {"3": "COSMO-SkyMed"}}


def test_sensor_comes_from_the_filename_when_the_name_carries_one():
    rows, _, _ = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 1], "Sensor_ID": [3, 3]}),
                       domain_lookup=SENSOR_ID_DOMAIN)
    assert list(rows["sensor"]) == ["Sentinel-1", "Sentinel-1"]
    assert list(rows["sensor_method"]) == ["filename", "filename"]


def test_sensor_falls_back_to_the_polygon_attribute_and_says_so():
    """The filename grammar never sees COSMO-SkyMed; the Sensor_ID domain does.
    Without `sensor_method` a consumer could not tell the two paths apart."""
    gdf = make_gdf({"Water_Class": [1, 1], "Sensor_ID": [3, 3]})
    rows, _, _ = build(SENSORLESS_FLOOD_LAYER, gdf, domain_lookup=SENSOR_ID_DOMAIN)
    assert list(rows["sensor"]) == ["COSMO-SkyMed", "COSMO-SkyMed"]
    assert list(rows["sensor_method"]) == ["attribute", "attribute"]

    ln = grammar.parse(SENSORLESS_FLOOD_LAYER)
    groups = silver.layer_acquisitions(ln, gdf)
    srcs = silver.source_rows("FL20190314MOZ", ln, groups, domain_lookup=SENSOR_ID_DOMAIN)
    assert [(r["sensor"], r["sensor_method"]) for r in srcs] == [("COSMO-SkyMed", "attribute")]


def test_sensor_method_is_none_when_neither_side_names_one():
    rows, _, _ = build(SENSORLESS_FLOOD_LAYER, make_gdf({"Water_Class": [1, 1]}))
    assert list(rows["sensor"]) == [None, None]
    assert list(rows["sensor_method"]) == ["none", "none"]


def test_coverage_rows_carry_sensor_provenance_too():
    gdf = make_gdf({"SensorDate": [pd.Timestamp("2019-03-30")] * 2, "Sensor_ID": [3, 3]})
    rows, _, _ = build("Beira_20190330_AnalysisExtent_MOZ", gdf, domain_lookup=SENSOR_ID_DOMAIN)
    assert list(rows["sensor"]) == ["COSMO-SkyMed", "COSMO-SkyMed"]
    assert list(rows["sensor_method"]) == ["attribute", "attribute"]


def test_sibling_check_reports_a_real_comparison():
    layers_df = pd.DataFrame(
        [{"sha256": "g1", "layer": "A"}, {"sha256": "g1", "layer": "B"},
         {"sha256": "s1", "layer": "A"}, {"sha256": "s1", "layer": "C"}]
    )
    status_df = pd.DataFrame([{"sha256": "s1", "status": "ok"}])
    assert silver.sibling_check(layers_df, status_df, "g1", ["s1"]) == (["B", "C"], "ok")


def test_sibling_check_refuses_to_claim_agreement_when_the_shp_was_never_listed():
    layers_df = pd.DataFrame([{"sha256": "g1", "layer": "A"}])
    status_df = pd.DataFrame([{"sha256": "s1", "status": "zip_unreadable"}])
    assert silver.sibling_check(layers_df, status_df, "g1", ["s1"]) == (None, "zip_unreadable")
    # no status row at all is its own state, not "they agree"
    assert silver.sibling_check(layers_df, pd.DataFrame(columns=["sha256", "status"]), "g1",
                                ["s1"]) == (None, "absent")
    # and no sibling at all means there was nothing to compare
    assert silver.sibling_check(layers_df, status_df, "g1", []) == (None, None)


def test_processing_frame_has_the_documented_columns():
    _, _, record = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 5]}))
    frame = silver.processing_frame([record])
    assert list(frame.columns) == silver.PROCESSING_COLUMNS
    assert frame["status"].tolist() == ["ok"]


def ledger_rows(*rows: dict) -> pd.DataFrame:
    """A minimal `resources.parquet` carrying only the columns `select_units`
    reads."""
    defaults = {"scope": "flood", "status": "uploaded", "event_code": "FL20190314MOZ"}
    return pd.DataFrame([defaults | r for r in rows])


def test_select_units_prefers_the_geodatabase_and_notes_its_shp_sibling():
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1"},
        {"dataset_id": "d1", "sha256": "s1", "resource_name": "a_SHP.zip",
         "format": "SHP", "target_id": "t2"},
    )
    (unit,) = silver.select_units(ledger)
    assert unit["sha256"] == "g1"
    assert unit["geometry_source"] == "gdb"
    assert unit["sibling_shp_sha256s"] == ["s1"]
    assert unit["code_method"] == "resource_name"


def test_select_units_falls_back_to_shp_when_a_dataset_has_no_gdb():
    ledger = ledger_rows(
        {"dataset_id": "d2", "sha256": "s2", "resource_name": "b_SHP.zip",
         "format": "SHP", "target_id": "t3"},
    )
    (unit,) = silver.select_units(ledger)
    assert (unit["sha256"], unit["geometry_source"]) == ("s2", "shp")
    assert unit["sibling_shp_sha256s"] == []


def test_select_units_collects_every_target_that_shipped_one_content():
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1"},
        {"dataset_id": "d3", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t9"},
    )
    (unit,) = silver.select_units(ledger)
    assert unit["target_ids"] == ["t1", "t9"]


def test_select_units_ignores_other_scopes_and_unuploaded_resources():
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1", "status": "pending"},
        {"dataset_id": "d2", "sha256": "g2", "resource_name": "c_GDB.zip",
         "format": "Geodatabase", "target_id": "t2", "scope": "other"},
        {"dataset_id": "d3", "sha256": "x1", "resource_name": "d.xlsx",
         "format": "XLSX", "target_id": "t3"},
    )
    assert silver.select_units(ledger) == []


def _two_code_ledger() -> pd.DataFrame:
    """One content listed under two event codes — the real FL20250812CPV /
    FL20250812COD case (an ISO3 typo), with the CPV listing the newer one."""
    return ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_COD_GDB.zip",
         "format": "Geodatabase", "target_id": "t1", "event_code": "FL20250812COD",
         "last_modified": "2025-08-13T09:00:00"},
        {"dataset_id": "d2", "sha256": "g1", "resource_name": "a_CPV_GDB.zip",
         "format": "Geodatabase", "target_id": "t2", "event_code": "FL20250812CPV",
         "last_modified": "2025-08-13T09:28:00"},
    )


def test_select_units_takes_the_latest_listing_when_a_content_has_two_codes():
    (unit,) = silver.select_units(_two_code_ledger())
    assert unit["code"] == "FL20250812CPV"
    assert unit["codes_listed"] == ["FL20250812COD", "FL20250812CPV"]


def test_select_units_honours_a_checked_code_override(monkeypatch):
    # the override wins over the timestamp, so a checked decision is not undone
    # by a later re-listing of the wrong code
    monkeypatch.setitem(silver.CODE_OVERRIDES, "g1", "FL20250812COD")
    (unit,) = silver.select_units(_two_code_ledger())
    assert unit["code"] == "FL20250812COD"
    assert unit["codes_listed"] == ["FL20250812COD", "FL20250812CPV"]


def test_the_seeded_override_covers_the_content_the_real_run_tripped_on():
    sha = "09ab92a146c0cf431ddb84241db45ecbb6de03f5718c5c52b52c44757c616a07"
    assert silver.CODE_OVERRIDES[sha] == "FL20250812CPV"


def test_processing_rows_carry_every_listed_code():
    _, _, record = build(
        FLOOD_LAYER, make_gdf({"Water_Class": [1, 1]}),
        codes_listed=["FL20250812COD", "FL20250812CPV"],
    )
    assert record["codes_listed"] == ["FL20250812COD", "FL20250812CPV"]
    # with nothing passed, the chosen code is the only one that was listed
    _, _, plain = build(FLOOD_LAYER, make_gdf({"Water_Class": [1, 1]}))
    assert plain["codes_listed"] == ["FL20190314MOZ"]


def test_select_units_rejects_a_content_with_no_event_code():
    ledger = ledger_rows(
        {"dataset_id": "d1", "sha256": "g1", "resource_name": "a_GDB.zip",
         "format": "Geodatabase", "target_id": "t1", "event_code": None},
    )
    with pytest.raises(ValueError, match="no event code"):
        silver.select_units(ledger)


def test_layer_mismatch_reports_names_missing_from_either_side():
    assert silver.layer_mismatch({"a", "b"}, {"a", "b"}) == []
    assert silver.layer_mismatch({"a", "b"}, {"a", "c"}) == ["b", "c"]


def test_prescreen_decides_what_it_can_before_a_read():
    assert silver.prescreen(grammar.parse(SKIP_LAYER), "Polygon") == "skipped_non_water"
    assert silver.prescreen(grammar.parse("ST1_Mystery_Zone"), "Polygon") == "unclassified"
    assert silver.prescreen(grammar.parse(FLOOD_LAYER), "Point") == "skipped_non_water"
    assert silver.prescreen(grammar.parse(FLOOD_LAYER), "Polygon") is None
    # unknown geometry type (a shapefile member) must be read, not assumed
    assert silver.prescreen(grammar.parse(FLOOD_LAYER), None) is None


def test_merge_processing_replaces_rows_for_the_same_layer():
    first = silver.processing_row(
        sha256="a", layer="L1", code="C", code_method="resource_name",
        status="unreadable", geometry_source="gdb", target_ids=[],
    )
    other = silver.processing_row(
        sha256="a", layer="L2", code="C", code_method="resource_name",
        status="ok", geometry_source="gdb", target_ids=[],
    )
    frame = silver.merge_processing(silver.processing_frame([first, other]), [first | {
        "status": "ok"}])
    assert len(frame) == 2
    assert sorted(frame["status"]) == ["ok", "ok"]
    assert list(frame.columns) == silver.PROCESSING_COLUMNS


def test_build_layer_rejects_a_layer_it_cannot_reproject():
    gdf = gpd.GeoDataFrame({"Water_Class": [1, 1]}, geometry=SQUARES, crs=None)
    with pytest.raises(ValueError, match="has no CRS"):
        build(FLOOD_LAYER, gdf)


# --- the CLI ---------------------------------------------------------------
# `pipelines/` is not a package, so the script is loaded by path (the pattern
# tests/unosat/test_harvest.py established).

SHA = "c" * 64
ZIP_NAME = "FL20190314MOZ_SHP.zip"


def _load_cli():
    spec = importlib.util.spec_from_file_location("unosat_silver_cli", _CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shp_zip(tmp_path: Path) -> tuple[Path, list[str]]:
    """A shapefile zip carrying one flood layer and one damage layer."""
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    frames = {
        FLOOD_LAYER: gpd.GeoDataFrame(
            {"Water_Clas": [1, 1], "d_Water_Cl": ["Flood Water", "Flood Water"]},
            geometry=SQUARES,
            crs="EPSG:4326",
        ),
        SKIP_LAYER: gpd.GeoDataFrame({"a": [1]}, geometry=SQUARES[:1], crs="EPSG:4326"),
    }
    for name, frame in frames.items():
        frame.to_file(shp_dir / f"{name}.shp", driver="ESRI Shapefile")
    zip_path = tmp_path / ZIP_NAME
    members = []
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in sorted(shp_dir.iterdir()):
            member = f"{ZIP_NAME[:-4]}/{f.name}"
            z.write(f, arcname=member)
            members.append(member)
    return zip_path, members


def _work_dir(tmp_path: Path, members: list[str]) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    row = dict.fromkeys(common.LEDGER_COLS)
    row.update(
        target_id="res-1@2024-01-01T00:00:00", dataset_id="d1", resource_name=ZIP_NAME,
        format="SHP", event_code="FL20190314MOZ", scope="flood", status="uploaded", sha256=SHA,
    )
    pd.DataFrame([row]).to_parquet(work / "resources.parquet")
    pd.DataFrame(
        [{"sha256": SHA, "member": m, "target_id": row["target_id"]} for m in members]
    ).to_parquet(work / "zip_contents.parquet")
    layers.persist_frames(
        work,
        pd.DataFrame(layers.layers_from_zip_members(SHA, ZIP_NAME, members)),
        pd.DataFrame([layers.status_row(SHA, "ok")]),
    )
    domains.persist_frames(
        work,
        pd.DataFrame(columns=domains.ROWS_COLUMNS),
        pd.DataFrame(columns=domains.STATUS_COLUMNS),
    )
    return work


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """The CLI wired to a MemoryStore and a local zip, with no Azure at all."""
    zip_path, members = _shp_zip(tmp_path)
    work = _work_dir(tmp_path, members)
    module = _load_cli()
    store = MemoryStore()
    monkeypatch.setattr(module.meta, "bootstrap", lambda work_dir, stage: object())
    monkeypatch.setattr(module.common, "global_settings", lambda stage: None)
    monkeypatch.setattr(module.blobio, "uploader", lambda settings: None)
    monkeypatch.setattr(module.store, "DataLakeStore", lambda fs, cc: store)
    monkeypatch.setattr(module.cache, "read_through", lambda sha, name, fetch: zip_path)
    return module, store, work


def _layer_blobs(store: MemoryStore) -> list[str]:
    return sorted(p for p in store.uploads if "/layer=" in p)


def test_cli_writes_one_file_per_layer_and_records_every_layer(cli_env):
    module, store, work = cli_env
    module.main(["--work-dir", str(work)])

    (blob,) = _layer_blobs(store)
    assert blob.startswith(f"{common.SILVER}/observed_event/code=FL20190314MOZ/layer=")
    rows = gpd.read_parquet(io.BytesIO(store.uploads[blob]))
    assert list(rows["layer_kind"]) == ["flood", "flood"]
    assert list(rows["geometry_source"]) == ["shp", "shp"]

    proc = pd.read_parquet(work / silver.PROCESSING_FILE)
    assert dict(zip(proc["layer"], proc["status"], strict=True)) == {
        FLOOD_LAYER: "ok",
        SKIP_LAYER: "skipped_non_water",
    }
    assert f"{common.SILVER_META}/processing.parquet" in store.uploads
    assert silver.sources_path("FL20190314MOZ") in store.uploads


def test_cli_resumes_from_the_processing_ledger(cli_env, capsys):
    module, store, work = cli_env
    module.main(["--work-dir", str(work)])
    before = dict(store.uploads)
    module.main(["--work-dir", str(work)])
    assert "to process: 0" in capsys.readouterr().out
    assert store.uploads == before


def test_cli_skips_a_layer_whose_content_is_already_in_silver(cli_env):
    module, store, work = cli_env
    module.main(["--work-dir", str(work)])
    (blob,) = _layer_blobs(store)
    written = store.uploads[blob]

    # the ledger is lost but blob is not: the second run re-reads and re-hashes
    # the layer, finds its file already there, and records the reuse
    (work / silver.PROCESSING_FILE).unlink()
    sentinel = b"sentinel: must not be overwritten"
    store.uploads[blob] = sentinel
    module.main(["--work-dir", str(work)])

    assert store.uploads[blob] == sentinel != written
    proc = pd.read_parquet(work / silver.PROCESSING_FILE)
    reused = proc[proc["layer"] == FLOOD_LAYER].iloc[0]
    assert bool(reused["reused"]) is True
    assert reused["status"] == "ok"
    assert reused["n_polygons"] == 2


def test_cli_codes_filter_selects_nothing_for_an_unknown_code(cli_env, capsys):
    module, store, work = cli_env
    module.main(["--work-dir", str(work), "--codes", "FL20200101SSD"])
    assert "source zips: 0" in capsys.readouterr().out
    assert _layer_blobs(store) == []


def test_cli_force_revisits_done_layers_without_rewriting_their_files(cli_env):
    module, store, work = cli_env
    module.main(["--work-dir", str(work)])
    (blob,) = _layer_blobs(store)
    sentinel = b"sentinel: must not be overwritten"
    store.uploads[blob] = sentinel
    del store.uploads[silver.sources_path("FL20190314MOZ")]

    module.main(["--work-dir", str(work), "--force"])

    # the layer file is reused, but the sources table this run rebuilt is back
    assert store.uploads[blob] == sentinel
    assert silver.sources_path("FL20190314MOZ") in store.uploads
    proc = pd.read_parquet(work / silver.PROCESSING_FILE)
    assert len(proc) == 2


def test_cli_raises_when_the_layer_inventory_is_missing(cli_env):
    """An absent inventory is a prerequisite we failed to run, not "no layers":
    silently processing nothing would look like a clean run."""
    module, _, work = cli_env
    (work / "layers.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="run pipelines/unosat/layers.py first"):
        module.main(["--work-dir", str(work)])


def test_cli_records_that_there_was_no_shp_sibling_to_compare(cli_env):
    module, _, work = cli_env
    module.main(["--work-dir", str(work)])
    proc = pd.read_parquet(work / silver.PROCESSING_FILE)
    # this fixture is SHP-sourced, so no GDB/SHP cross-check applies at all
    assert proc["shp_gdb_mismatch"].isna().all()
    assert proc["sibling_status"].isna().all()
