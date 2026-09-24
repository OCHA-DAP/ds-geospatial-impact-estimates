import json
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import Polygon

from gie.unosat import domains, readers

GDB_WRITE_SUPPORTED = pyogrio.list_drivers(write=True).get("OpenFileGDB") is not None

SQUARE_A = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
SQUARE_B = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])


def make_shp_zip(tmp_path: Path, crs: str) -> tuple[Path, str]:
    """Write a two-feature shapefile in `crs`, zip it, return (zip_path, member)."""
    gdf = gpd.GeoDataFrame(
        {"Water_Class": [0, 1], "OBJECTID": [1, 2]},
        geometry=[SQUARE_A, SQUARE_B],
        crs=crs,
    )
    shp_dir = tmp_path / "shpdir"
    shp_dir.mkdir()
    shp_path = shp_dir / "layer.shp"
    gdf.to_file(shp_path, driver="ESRI Shapefile")
    zip_path = tmp_path / "archive.zip"
    member = "sub/layer.shp"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in shp_dir.iterdir():
            z.write(f, arcname=f"sub/{f.name}")
    return zip_path, member


def test_read_shp_member_reads_geometry_and_attrs(tmp_path):
    zip_path, member = make_shp_zip(tmp_path, crs="EPSG:32636")
    gdf = readers.read_shp_member(zip_path, member)
    assert len(gdf) == 2
    assert gdf.crs.to_string() == "EPSG:32636"
    assert set(gdf["OBJECTID"]) == {1, 2}


def test_to_wgs84_reprojects_and_reports_source_crs(tmp_path):
    zip_path, member = make_shp_zip(tmp_path, crs="EPSG:32636")
    gdf = readers.read_shp_member(zip_path, member)
    reprojected, source_crs = readers.to_wgs84(gdf, "layer")
    assert source_crs == "EPSG:32636"
    assert reprojected.crs.to_epsg() == 4326
    # geometry actually moved (32636 is a projected CRS, not equal to WGS84 coords)
    assert not reprojected.geometry.iloc[0].equals(gdf.geometry.iloc[0])


def test_to_wgs84_noop_still_reports_epsg4326(tmp_path):
    gdf = gpd.GeoDataFrame({"a": [1]}, geometry=[SQUARE_A], crs="EPSG:4326")
    reprojected, source_crs = readers.to_wgs84(gdf, "layer")
    assert source_crs == "EPSG:4326"
    assert reprojected.crs.to_epsg() == 4326


def test_to_wgs84_raises_naming_layer_when_crs_missing():
    gdf = gpd.GeoDataFrame({"a": [1]}, geometry=[SQUARE_A], crs=None)
    with pytest.raises(ValueError, match="mystery_layer"):
        readers.to_wgs84(gdf, "mystery_layer")


@pytest.mark.skipif(not GDB_WRITE_SUPPORTED, reason="OpenFileGDB driver cannot write in this env")
def test_read_gdb_layer_round_trips_tz_aware_datetime(tmp_path):
    gdf = gpd.GeoDataFrame(
        {
            "Water_Class": [0, 1],
            "dt": pd.to_datetime(["2021-01-01T00:00:00Z", "2021-01-02T00:00:00Z"]),
        },
        geometry=[SQUARE_A, SQUARE_B],
        crs="EPSG:4326",
    )
    gdb_path = tmp_path / "test.gdb"
    pyogrio.write_dataframe(gdf, gdb_path, driver="OpenFileGDB", layer="mylayer")

    read = readers.read_gdb_layer(gdb_path, "mylayer")
    assert len(read) == 2
    assert str(read["dt"].dt.tz) != "None"
    assert set(read["Water_Class"]) == {0, 1}


def test_extract_gdbs_is_reused_from_domains_not_duplicated():
    # readers.py must not carry its own extraction logic; it imports domains'.
    assert readers.extract_gdbs is domains.extract_gdbs


def _gdf(rows: list[dict]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def test_content_hash_ignores_row_order():
    rows = [
        {"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1},
        {"geometry": SQUARE_B, "Water_Class": 1, "OBJECTID": 2},
    ]
    forward = _gdf(rows)
    backward = _gdf(list(reversed(rows)))
    assert readers.content_hash(forward) == readers.content_hash(backward)


def test_content_hash_changes_when_attribute_changes():
    base = _gdf([{"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1}])
    changed = _gdf([{"geometry": SQUARE_A, "Water_Class": 1, "OBJECTID": 1}])
    assert readers.content_hash(base) != readers.content_hash(changed)


def test_content_hash_changes_when_geometry_changes():
    base = _gdf([{"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1}])
    changed = _gdf([{"geometry": SQUARE_B, "Water_Class": 0, "OBJECTID": 1}])
    assert readers.content_hash(base) != readers.content_hash(changed)


def test_content_hash_handles_a_feature_with_no_geometry():
    """UNOSAT geodatabases contain attribute rows carrying no shape. That is a
    real state of the data, not a read failure, so hashing must not raise."""
    with_null = _gdf(
        [
            {"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1},
            {"geometry": None, "Water_Class": 1, "OBJECTID": 2},
        ]
    )
    assert len(readers.content_hash(with_null)) == 64


def test_content_hash_does_not_drop_a_geometryless_feature():
    """Hashing a null geometry as a sentinel rather than skipping the row is
    what keeps two layers that differ only in such rows distinguishable."""
    with_null = _gdf(
        [
            {"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1},
            {"geometry": None, "Water_Class": 1, "OBJECTID": 2},
        ]
    )
    without = _gdf([{"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1}])
    assert readers.content_hash(with_null) != readers.content_hash(without)


def test_content_hash_distinguishes_null_geometry_rows_by_attributes():
    """Two geometryless rows are the same content only when their attributes
    match, so the sentinel must not flatten them together."""
    a = _gdf([{"geometry": None, "Water_Class": 0, "OBJECTID": 1}])
    b = _gdf([{"geometry": None, "Water_Class": 1, "OBJECTID": 1}])
    assert readers.content_hash(a) != readers.content_hash(b)


def test_content_hash_ignores_objectid_only_difference():
    a = _gdf([{"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 1}])
    b = _gdf([{"geometry": SQUARE_A, "Water_Class": 0, "OBJECTID": 999}])
    assert readers.content_hash(a) == readers.content_hash(b)


def test_content_hash_ignores_mixed_case_hash_exclude_columns():
    # real exports vary casing: GDB names the field `Shape_Length`, shapefiles
    # truncate it to `Shape_Leng` — the exclusion must match case-insensitively.
    a = _gdf(
        [{"geometry": SQUARE_A, "Water_Class": 0, "Shape_Length": 4.0, "OBJECTID": 1}]
    )
    b = _gdf(
        [{"geometry": SQUARE_A, "Water_Class": 0, "Shape_Length": 9.9, "OBJECTID": 999}]
    )
    assert readers.content_hash(a) == readers.content_hash(b)


def test_content_hash_ignores_shape_area_and_length_artifacts():
    a = _gdf(
        [{"geometry": SQUARE_A, "Water_Class": 0, "SHAPE_Area": 1.0, "SHAPE_Length": 4.0}]
    )
    b = _gdf(
        [{"geometry": SQUARE_A, "Water_Class": 0, "SHAPE_Area": 2.5, "SHAPE_Length": 9.9}]
    )
    assert readers.content_hash(a) == readers.content_hash(b)


def test_attrs_json_excludes_geometry_and_serialises_datetime():
    row = pd.Series(
        {"geometry": SQUARE_A, "Water_Class": 0, "acquired": pd.Timestamp("2021-01-01", tz="UTC")}
    )
    text = readers.attrs_json(row)
    assert "geometry" not in text
    assert "2021-01-01" in text


def test_attrs_json_keeps_hash_exclude_columns_verbatim_for_storage():
    # attrs_json itself does not filter HASH_EXCLUDE columns — that filtering
    # is content_hash's job, so the stored attrs_json keeps OBJECTID etc.
    row = pd.Series({"geometry": SQUARE_A, "OBJECTID": 42, "Water_Class": 0})
    text = readers.attrs_json(row)
    assert "42" in text and "OBJECTID" in text


def test_attrs_json_serialises_nan_and_nat_as_json_null():
    row = pd.Series(
        {"geometry": SQUARE_A, "missing_value": float("nan"), "missing_date": pd.NaT}
    )
    text = readers.attrs_json(row)
    parsed = json.loads(text)  # raises if the text is not valid JSON (e.g. bare NaN)
    assert parsed["missing_value"] is None
    assert parsed["missing_date"] is None
