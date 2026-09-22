"""Gold v2 (spec §4): silver polygon rows dissolved into label sets.

Every fixture here is a synthetic silver frame — the columns silver writes,
nothing read from blob — so the rules can be exercised one at a time.
"""

import importlib.util
import io
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from gie.unosat import common, gold, silver
from gie.unosat.store import MemoryStore

_CLI_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "unosat" / "gold.py"

CODE = "FL20190314MOZ"
META = {"name": "Mozambique: Tropical Cyclone Idai", "countries": "MOZ"}
FLOOD_LAYER = "ST1_20190330_FloodExtent_Beira_MOZ"
WATER_LAYER = "ST1_20190330_WaterExtent_Beira_MOZ"
MAX_LAYER = "ST1_20190330_MaximumFloodWaterExtent_Beira_MOZ"
FOOTPRINT_LAYER = "ST1_20190330_AnalysisExtent_Beira_MOZ"
CLOUD_LAYER = "ST1_20190330_CloudObstruction_Beira_MOZ"

# Disjoint unit squares, so a union's area is the count of its parts and an
# overlap or a missing part is visible in the area alone.
A, B, C, D = box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1), box(6, 0, 7, 1)
BIG = box(-1, -1, 8, 2)  # contains all four


def _frame(rows: list[dict], columns: list[str]) -> gpd.GeoDataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    frame["geometry"] = gpd.GeoSeries(frame["geometry"].tolist(), crs="EPSG:4326")
    for col in ("acq_datetime", "acq_window_start", "acq_window_end"):
        frame[col] = pd.to_datetime(frame[col])
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")


def observed(*rows: dict) -> gpd.GeoDataFrame:
    defaults = {
        "code": CODE,
        "layer_name": FLOOD_LAYER,
        "layer_kind": "flood",
        "area_label": "Beira_MOZ",
        "sensor": "Sentinel-1",
        "acq_datetime": datetime(2019, 3, 30),
        "acq_precision": "date",
        "acq_method": "filename",
        "acq_conflict": False,
        "target_ids": ["r-1@2019-04-01T00:00:00"],
        "confidence": "High",
        "water_status": "Observed",
        "geometry": A,
    }
    return _frame([defaults | row for row in rows or ({},)], silver.OBSERVED_COLUMNS)


def coverage(*rows: dict) -> gpd.GeoDataFrame:
    defaults = {
        "code": CODE,
        "layer_name": FOOTPRINT_LAYER,
        "role": "footprint",
        "sensor": "Sentinel-1",
        "acq_datetime": datetime(2019, 3, 30),
        "acq_precision": "date",
        "acq_method": "filename",
        "acq_conflict": False,
        "target_ids": ["r-1@2019-04-01T00:00:00"],
        "geometry": BIG,
    }
    return _frame([defaults | row for row in rows or ({},)], silver.COVERAGE_COLUMNS)


def build(obs, cov=None):
    return gold.build_code(CODE, obs, cov if cov is not None else coverage(), META)


# --- the geometry rules ----------------------------------------------------


def test_water_is_flood_and_pre_flood_dissolved_together():
    """The fusion target: everything wet at acquisition, whatever produced it."""
    labels, index = build(
        observed(
            {"layer_kind": "flood", "geometry": A},
            {"layer_kind": "water_pre", "geometry": B},
            {"layer_kind": "water", "geometry": C},
        )
    )
    (row,) = labels.itertuples()
    assert row.geom_water.equals(A.union(B).union(C))
    assert row.geom_flood.equals(A)
    assert index["n_polygons"].iloc[0] == 3
    # three unit squares at the equator, in km2: ~111 km a side
    assert index["water_area_km2"].iloc[0] == pytest.approx(3 * 12365, rel=0.02)
    assert index["flood_area_km2"].iloc[0] == pytest.approx(12365, rel=0.02)


def test_possible_flood_is_its_own_geometry_and_not_water():
    """Possible flood-affected land is a different claim from observed water;
    folding it into `geom_water` would inflate every label that has it."""
    labels, index = build(
        observed(
            {"layer_kind": "flood", "geometry": A},
            {"layer_kind": "flood_possible", "geometry": B},
        )
    )
    (row,) = labels.itertuples()
    assert row.geom_water.equals(A)
    assert row.geom_possible.equals(B)
    assert index["possible_area_km2"].iloc[0] > 0


def test_flood_is_null_when_the_source_never_separated_it():
    """A WaterExtent layer with no per-polygon class says "water here", not
    "flood here". Null is the honest answer; an empty geometry would read as
    "no flood was found"."""
    labels, index = build(observed({"layer_name": WATER_LAYER, "layer_kind": "water"}))
    (row,) = labels.itertuples()
    assert row.geom_flood is None
    assert pd.isna(index["flood_area_km2"].iloc[0])


def test_flood_is_empty_not_null_when_a_flood_layer_found_none():
    """A FloodExtent layer whose polygons all resolved to pre-flood water DID
    separate flood — it found none. Zero and unknown are different states."""
    labels, index = build(observed({"layer_name": FLOOD_LAYER, "layer_kind": "water_pre"}))
    (row,) = labels.itertuples()
    assert row.geom_flood is not None and row.geom_flood.is_empty
    assert index["flood_area_km2"].iloc[0] == 0.0


def test_aggregate_and_other_water_rows_are_excluded_and_counted():
    """Cumulative maxima are not a snapshot of anything; `other_water`
    (aquaculture, swamp, snow) is not flood. Both stay out of every geometry
    and are counted so a reader can see what the label left behind."""
    labels, index = build(
        observed(
            {"layer_kind": "flood", "geometry": A},
            {"layer_name": MAX_LAYER, "layer_kind": "aggregate_max", "geometry": B},
            {"layer_name": MAX_LAYER, "layer_kind": "aggregate_min", "geometry": C},
            {"layer_kind": "other_water", "geometry": D},
        )
    )
    (row,) = labels.itertuples()
    assert row.geom_water.equals(A)
    assert index["excluded_aggregate_n"].iloc[0] == 3
    assert index["n_polygons"].iloc[0] == 1
    assert index["product_classes"].iloc[0] == "flood"


def test_a_group_of_only_excluded_rows_keeps_a_row_with_no_geometry():
    """Dropping it would lose the only record that those polygons existed."""
    labels, index = build(
        observed({"layer_name": MAX_LAYER, "layer_kind": "aggregate_max", "geometry": A})
    )
    (row,) = labels.itertuples()
    assert row.geom_water is None and row.geom_flood is None and row.geom_possible is None
    assert index["n_polygons"].iloc[0] == 0
    assert index["excluded_aggregate_n"].iloc[0] == 1
    # and no sensor: `sensor` names the instrument behind the label geometries,
    # and this set produced none, so there is nothing to attribute to one
    assert pd.isna(index["sensor"].iloc[0])
    assert index["sensor_class"].iloc[0] == "unknown"


# --- the valid mask --------------------------------------------------------


def test_valid_mask_is_the_footprint_minus_the_clouds():
    labels, index = build(
        observed({"geometry": A}),
        coverage(
            {"role": "footprint", "geometry": BIG},
            {"layer_name": CLOUD_LAYER, "role": "not_analysed", "geometry": D},
        ),
    )
    (row,) = labels.itertuples()
    assert row.valid_basis == "footprint_minus_cloud"
    assert row.valid_match == "interval"
    assert row.geom_valid.equals(BIG.difference(D))
    assert not row.geom_valid.intersects(D.centroid)
    _, unmasked = build(observed({"geometry": A}), coverage({"geometry": BIG}))
    assert index["valid_area_km2"].iloc[0] < unmasked["valid_area_km2"].iloc[0]


def test_valid_mask_is_the_bare_footprint_when_nothing_was_masked():
    labels, _ = build(observed(), coverage({"role": "footprint", "geometry": BIG}))
    (row,) = labels.itertuples()
    assert row.valid_basis == "footprint"
    assert row.geom_valid.equals(BIG)


def test_no_footprint_for_the_interval_is_valid_basis_none():
    """`not_analysed` alone says what was NOT looked at, not what was."""
    labels, index = build(
        observed(),
        coverage({"layer_name": CLOUD_LAYER, "role": "not_analysed", "geometry": D}),
    )
    (row,) = labels.itertuples()
    assert row.valid_basis == "none"
    assert row.geom_valid is None
    assert pd.isna(index["valid_area_km2"].iloc[0])


def test_a_footprint_for_another_area_does_not_mask_this_one():
    """Area is never crossed, however the products relate: a different AOI's
    footprint would claim unobserved ground as observed."""
    elsewhere = FOOTPRINT_LAYER.replace("Beira_MOZ", "Buzi_MOZ")
    labels, _ = build(observed(), coverage({"layer_name": elsewhere, "geometry": BIG}))
    (row,) = labels.itertuples()
    assert row.valid_basis == "none"


def test_a_footprint_from_another_product_does_not_mask_this_one():
    """No shared `target_id` means the footprint describes a different
    delivery; nothing links it to these polygons."""
    labels, _ = build(observed(), coverage({"target_ids": ["r-99@2020-01-01T00:00:00"]}))
    (row,) = labels.itertuples()
    assert row.valid_basis == "none"


def test_a_footprint_from_the_same_product_masks_a_different_interval():
    """The interval is a refinement, not a gate. A footprint layer usually
    carries only its filename's date while the observed layer's per-polygon
    dates widen its interval, so demanding equal intervals leaves most real
    label sets with no mask at all; `valid_match` records which it was."""
    labels, index = build(observed(), coverage({"acq_datetime": datetime(2019, 4, 2)}))
    (row,) = labels.itertuples()
    assert row.valid_basis == "footprint"
    assert row.valid_match == "product"
    assert index["valid_area_km2"].iloc[0] > 0


def test_an_exact_interval_footprint_wins_over_a_product_only_one():
    """Where the finer match exists, it is the one used."""
    labels, _ = build(
        observed(),
        coverage(
            {"geometry": BIG, "acq_datetime": datetime(2019, 4, 2)},
            {"geometry": A, "acq_datetime": datetime(2019, 3, 30)},
        ),
    )
    (row,) = labels.itertuples()
    assert row.valid_match == "interval"
    assert row.geom_valid.equals(A)


def test_refining_never_throws_away_the_only_footprint():
    """An exact-interval subset that holds nothing but cloud is not a better
    mask — it is no mask. The product-and-area match still stands."""
    labels, _ = build(
        observed(),
        coverage(
            {"geometry": BIG, "acq_datetime": datetime(2019, 4, 2)},
            {
                "layer_name": CLOUD_LAYER,
                "role": "not_analysed",
                "geometry": D,
                "acq_datetime": datetime(2019, 3, 30),
            },
        ),
    )
    (row,) = labels.itertuples()
    assert row.valid_basis == "footprint_minus_cloud"
    assert row.valid_match == "product"
    assert row.geom_valid.equals(BIG.difference(D))


def test_valid_match_is_null_when_there_is_no_mask():
    labels, index = build(observed(), coverage({"target_ids": ["r-99@t"]}))
    assert pd.isna(labels["valid_match"].iloc[0])
    assert pd.isna(index["valid_match"].iloc[0])


# --- the grain -------------------------------------------------------------


def test_two_acquisition_intervals_make_two_label_sets():
    labels, index = build(
        observed(
            {"acq_datetime": datetime(2019, 3, 30), "geometry": A},
            {"acq_datetime": datetime(2019, 4, 2), "geometry": B},
        )
    )
    assert len(labels) == len(index) == 2
    assert list(index["acq_start"]) == [datetime(2019, 3, 30), datetime(2019, 4, 2)]
    assert [g.equals(h) for g, h in zip(labels["geom_water"], [A, B], strict=True)] == [True] * 2


def test_two_areas_on_one_date_make_two_label_sets():
    labels, index = build(
        observed(
            {"geometry": A},
            {"layer_name": FLOOD_LAYER.replace("Beira", "Buzi"), "area_label": "Buzi_MOZ"},
        )
    )
    assert list(index["aoi"]) == ["Beira_MOZ", "Buzi_MOZ"]
    assert len(labels) == 2


def test_the_window_columns_beat_the_point_date_for_the_interval():
    labels, index = build(
        observed(
            {
                "acq_datetime": None,
                "acq_window_start": datetime(2019, 3, 28),
                "acq_window_end": datetime(2019, 3, 31),
                "acq_precision": "window",
            }
        )
    )
    assert index["acq_start"].iloc[0] == datetime(2019, 3, 28)
    assert index["acq_end"].iloc[0] == datetime(2019, 3, 31)
    assert index["width_days"].iloc[0] == 3.0
    assert pd.isna(labels["label_day"].iloc[0])


def test_label_day_is_set_only_when_the_interval_fits_one_day():
    labels, index = build(
        observed(
            {"geometry": A},
            {
                "geometry": B,
                "acq_datetime": None,
                "acq_window_start": datetime(2019, 4, 1),
                "acq_window_end": datetime(2019, 4, 3),
                "acq_precision": "window",
            },
        )
    )
    assert index["label_day"].iloc[0] == labels["label_day"].iloc[0] == "2019-03-30"
    assert pd.isna(index["label_day"].iloc[1]) and pd.isna(labels["label_day"].iloc[1])
    assert list(index["width_days"]) == [0.0, 2.0]


def test_rows_with_no_date_at_all_never_reach_gold():
    """`acq_precision = "none"` is silver's record that a layer carried no date
    anywhere; such a row cannot be placed on any acquisition interval."""
    labels, index = build(
        observed(
            {"geometry": A},
            {"geometry": B, "acq_datetime": None, "acq_precision": "none"},
        )
    )
    (row,) = labels.itertuples()
    assert row.geom_water.equals(A)
    assert index["n_polygons"].iloc[0] == 1


def test_an_unknown_acquisition_precision_raises():
    """A value outside the vocabulary means silver changed under us; guessing
    which side of the "none" filter it belongs on would corrupt the grain."""
    with pytest.raises(ValueError, match="acq_precision"):
        build(observed({"acq_precision": "approximate"}))


def test_an_unknown_layer_kind_raises():
    """An unrecognised kind would not raise on its own: it would fall out of
    every `isin` above and leave a label set quietly missing polygons that no
    count mentions."""
    with pytest.raises(ValueError, match="layer_kind"):
        build(observed({"layer_kind": "damp"}))


def test_an_unknown_coverage_role_raises():
    with pytest.raises(ValueError, match="role"):
        build(observed(), coverage({"role": "partial"}))


def test_a_date_precision_row_with_no_date_raises():
    with pytest.raises(ValueError, match="no acquisition date"):
        build(observed({"acq_datetime": None}))


# --- the index -------------------------------------------------------------


def test_index_has_the_spec_columns_and_the_shared_label_source():
    _, index = build(observed())
    assert list(index.columns) == gold.INDEX_COLUMNS
    assert index["label_source"].iloc[0] == "unosat"
    assert index["code"].iloc[0] == CODE
    assert index["name"].iloc[0] == META["name"]
    assert index["countries"].iloc[0] == "MOZ"
    # UNOSAT ships neither of these; CEMS does, and the shared schema keeps
    # the columns so one reader serves both
    assert pd.isna(index["sensor_gsd"].iloc[0]) and pd.isna(index["det_methods"].iloc[0])


def test_a_label_set_built_from_two_sensors_is_classed_multiple():
    """`sensor` keeps the modal value for provenance, but calling a set built
    from a SAR pass and a VHR digitisation `sar` would tell a consumer one
    thing about a label that is two."""
    _, index = build(
        observed(
            {"sensor": "Sentinel-1", "geometry": A},
            {"sensor": "Sentinel-1", "geometry": B},
            {"sensor": "WorldView-2", "geometry": C},
        )
    )
    assert index["sensor"].iloc[0] == "Sentinel-1"
    assert index["sensor_class"].iloc[0] == "multiple"


def test_one_sensor_throughout_keeps_its_own_class():
    _, index = build(observed({"sensor": "Sentinel-1", "geometry": A}, {"geometry": B}))
    assert index["sensor_class"].iloc[0] == "sar"


def test_an_excluded_row_never_supplies_the_sensor():
    """The cumulative layer's instrument produced none of this label's
    geometry, so it must not end up named as the label's sensor."""
    _, index = build(
        observed(
            {"sensor": "VIIRS", "geometry": A},
            {"layer_name": MAX_LAYER, "layer_kind": "aggregate_max", "sensor": "Sentinel-1"},
            {"layer_name": MAX_LAYER, "layer_kind": "aggregate_max", "sensor": "Sentinel-1"},
        )
    )
    assert index["sensor"].iloc[0] == "VIIRS"
    assert index["sensor_class"].iloc[0] == "optical_coarse"


def test_sensor_class_tiers_a_coarse_automated_product_apart():
    _, index = build(observed({"sensor": "VIIRS"}))
    assert index["sensor_class"].iloc[0] == "optical_coarse"


def test_a_conflicting_acquisition_anywhere_in_the_group_marks_the_row():
    _, index = build(
        observed(
            {"geometry": A, "acq_conflict": False},
            {"geometry": B, "acq_conflict": True},
        )
    )
    assert bool(index["acq_conflict"].iloc[0]) is True
    assert index["acq_precision"].iloc[0] == "date"


def test_index_carries_the_bounds_and_the_provenance():
    _, index = build(
        observed(
            {"geometry": A, "target_ids": ["r-1@t"]},
            {"geometry": C, "target_ids": ["r-2@t", "r-1@t"]},
        )
    )
    row = index.iloc[0]
    assert (row["minx"], row["miny"], row["maxx"], row["maxy"]) == (0.0, 0.0, 5.0, 1.0)
    assert row["target_ids"] == "r-1@t; r-2@t"
    assert row["confidence"] == "High"
    assert row["water_status"] == "Observed"


def test_an_empty_silver_partition_yields_empty_frames_with_the_full_schema():
    """A code with no water polygons is a real state, reported as zero rows."""
    labels, index = build(_frame([], silver.OBSERVED_COLUMNS))
    assert len(labels) == 0 and len(index) == 0
    assert list(index.columns) == gold.INDEX_COLUMNS
    assert list(labels.columns) == gold.LABEL_COLUMNS


# --- the file -------------------------------------------------------------


def test_the_labels_file_round_trips_all_four_geometry_columns(tmp_path):
    """The multi-geometry GeoParquet is the whole point of gold v2: a reader
    must get water, flood, possible and the valid mask back as geometry, not
    as WKB in an object column."""
    labels, _ = build(
        observed(
            {"layer_kind": "flood", "geometry": A},
            {"layer_kind": "water_pre", "geometry": B},
            {"layer_kind": "flood_possible", "geometry": C},
        ),
        coverage(
            {"role": "footprint", "geometry": BIG},
            {"layer_name": CLOUD_LAYER, "role": "not_analysed", "geometry": D},
        ),
    )
    path = tmp_path / "gold" / "labels" / f"code={CODE}" / "data.parquet"
    silver.write_layer_local(path, labels)

    back = gold.read_labels_file(path)
    assert back.geometry.name == "geom_water"
    for col in gold.GEOMETRY_COLUMNS:
        assert isinstance(back[col], gpd.GeoSeries), col
        assert back[col].crs == "EPSG:4326"
        assert back[col].iloc[0].equals(labels[col].iloc[0]), col
    assert back["label_source"].iloc[0] == "unosat"


def test_a_stale_mirrored_index_part_is_refetched(tmp_path):
    """Unlike a silver layer file, an index part is rewritten in place when its
    code is rebuilt, so existence alone does not prove the mirror holds what
    blob holds — a stale part would be published into `label_index`."""
    blob_store = MemoryStore()
    work = tmp_path / "work"
    blob_path = gold.index_part_path(CODE)

    _, first = build(observed({"geometry": A}))
    silver.write_layer(blob_store, blob_path, first)
    (mirrored,) = gold.iter_index_parts(work, blob_store)
    assert len(pd.read_parquet(mirrored)) == 1

    # the code is rebuilt elsewhere: same path, different bytes
    _, rebuilt = build(observed({"geometry": A}, {"geometry": B, "area_label": "Buzi_MOZ"}))
    silver.write_layer(blob_store, blob_path, rebuilt)
    assert blob_store.exists_size(blob_path) != mirrored.stat().st_size

    (refetched,) = gold.iter_index_parts(work, blob_store)
    assert len(pd.read_parquet(refetched)) == 2


def test_concat_index_raises_on_a_part_from_an_older_schema(tmp_path):
    """Reindexing it into shape would fill the columns it lacks with nulls, and
    the published index would then assert something about those label sets
    that nobody measured."""
    _, index = build(observed())
    stale = tmp_path / "code=OLD.parquet"
    index.drop(columns=["valid_match"]).to_parquet(stale)

    with pytest.raises(ValueError, match=r"valid_match.*older gold schema"):
        gold.concat_index([stale])


def test_gold_paths_mirror_each_other():
    blob = gold.labels_path(CODE)
    assert blob == f"{common.GOLD}/labels/code={CODE}/data.parquet"
    assert gold.index_part_path(CODE) == f"{common.GOLD}/_index_parts/code={CODE}.parquet"
    assert gold.local_path("/w", blob) == Path(f"/w/gold/labels/code={CODE}/data.parquet")


def test_code_meta_summarises_the_resource_ledger():
    ledger = pd.DataFrame(
        [
            {"event_code": CODE, "dataset_name": "moz-idai", "iso3": "MOZ"},
            {"event_code": CODE, "dataset_name": "moz-idai", "iso3": "ZWE"},
            {"event_code": "FL20220424SSD", "dataset_name": "ssd-floods", "iso3": "SSD"},
        ]
    )
    got = gold.code_meta(ledger)
    assert got[CODE] == {"name": "moz-idai", "countries": "MOZ; ZWE"}
    assert got["FL20220424SSD"]["countries"] == "SSD"


# --- the CLI ---------------------------------------------------------------


def _load_cli():
    spec = importlib.util.spec_from_file_location("unosat_gold_cli", _CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """The CLI wired to a MemoryStore holding one code's silver partition."""
    blob_store = MemoryStore()
    work = tmp_path / "work"
    work.mkdir()
    pd.DataFrame(
        [{"event_code": CODE, "dataset_name": "moz-idai", "iso3": "MOZ", "status": "uploaded"}]
    ).to_parquet(work / "resources.parquet")

    obs = observed(
        {"layer_kind": "flood", "geometry": A}, {"layer_kind": "water_pre", "geometry": B}
    )
    silver.write_layer(
        blob_store, silver.silver_layer_path("observed_event", CODE, "a" * 64, "L"), obs
    )
    silver.write_layer(
        blob_store, silver.silver_layer_path("coverage", CODE, "b" * 64, "F"), coverage()
    )

    module = _load_cli()
    monkeypatch.setattr(module.meta, "bootstrap", lambda work_dir, stage: object())
    monkeypatch.setattr(module.common, "global_settings", lambda stage: None)
    monkeypatch.setattr(module.blobio, "uploader", lambda settings, **kw: None)
    monkeypatch.setattr(module.store, "DataLakeStore", lambda fs, cc: blob_store)
    return module, blob_store, work


def test_cli_writes_the_labels_the_index_part_and_the_whole_index(cli_env):
    module, blob_store, work = cli_env
    module.main(["--work-dir", str(work)])

    labels = gpd.read_parquet(io.BytesIO(blob_store.uploads[gold.labels_path(CODE)]))
    assert len(labels) == 1 and labels.geometry.name == "geom_water"
    # this code has no possible-flood polygons at all: the column must still
    # come back as geometry, not as an object column of nulls
    assert isinstance(labels["geom_possible"], gpd.GeoSeries)
    assert labels["geom_possible"].isna().all()
    part = pd.read_parquet(io.BytesIO(blob_store.uploads[gold.index_part_path(CODE)]))
    whole = pd.read_parquet(io.BytesIO(blob_store.uploads[gold.INDEX_PATH]))
    assert list(whole.columns) == gold.INDEX_COLUMNS
    assert len(whole) == len(part) == 1
    assert whole["water_area_km2"].iloc[0] > 0
    # mirrored locally first, exactly as silver does
    assert gold.local_path(work, gold.labels_path(CODE)).exists()


def test_cli_skips_a_code_already_built_but_still_rewrites_the_whole_index(cli_env):
    """Resumable per code: the expensive per-code build is skipped, while the
    index is always reassembled from every part in blob, so a resumed run
    never publishes an index covering only what it happened to rebuild."""
    module, blob_store, work = cli_env
    module.main(["--work-dir", str(work)])
    sentinel = b"sentinel: must not be rewritten"
    blob_store.uploads[gold.labels_path(CODE)] = sentinel
    del blob_store.uploads[gold.INDEX_PATH]

    module.main(["--work-dir", str(work)])

    assert blob_store.uploads[gold.labels_path(CODE)] == sentinel
    whole = pd.read_parquet(io.BytesIO(blob_store.uploads[gold.INDEX_PATH]))
    assert len(whole) == 1


def test_cli_force_rebuilds_a_code(cli_env):
    module, blob_store, work = cli_env
    module.main(["--work-dir", str(work)])
    blob_store.uploads[gold.labels_path(CODE)] = b"stale"

    module.main(["--work-dir", str(work), "--force"])

    assert blob_store.uploads[gold.labels_path(CODE)] != b"stale"


def test_cli_raises_for_a_code_with_no_silver_partition(cli_env):
    """An explicitly named code that silver never wrote is a mistake worth
    stopping for, not an empty gold partition to publish."""
    module, _, work = cli_env
    with pytest.raises(FileNotFoundError, match="no observed_event layer files"):
        module.main(["--work-dir", str(work), "--codes", "FL20200101SSD"])


def test_cli_limit_bounds_the_run(cli_env, capsys):
    module, blob_store, work = cli_env
    module.main(["--work-dir", str(work), "--limit", "0"])
    assert gold.labels_path(CODE) not in blob_store.uploads
