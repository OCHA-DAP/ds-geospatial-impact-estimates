import zipfile

import pandas as pd

from gie.unosat import layers

INFO = {"layers": [
    {"name": "VIIRS_20211119_20211123_FloodExtent_SouthSudan", "featureCount": 1,
     "geometryFields": [{"type": "MultiPolygon"}],
     "fields": [{"name": "Water_Class", "domainName": "Water_Class2"}, {"name": "Notes"}]},
    {"name": "Water_Class", "featureCount": 10, "geometryFields": [],
     "fields": [{"name": "Water_Class_code"}]},
]}


def test_layers_from_ogrinfo_keeps_geometry_layers_and_domain_bindings():
    rows = layers.layers_from_ogrinfo("s" * 64, "X_gdb.zip", INFO)
    assert [r["layer"] for r in rows] == [
        "VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Water_Class",
    ]
    r = rows[0]
    assert r["source"] == "gdb" and r["geometry_type"] == "MultiPolygon" and r["feature_count"] == 1
    assert r["fields"] == ["Water_Class", "Notes"]
    assert r["field_domains"] == {"Water_Class": "Water_Class2"}
    assert rows[1]["geometry_type"] is None  # a lookup table, no geometry


def test_layers_from_zip_members_one_row_per_shp():
    rows = layers.layers_from_zip_members(
        "s" * 64, "X_SHP.zip",
        ["A/ST_20180508_WaterExtent_X.shp", "A/ST_20180508_WaterExtent_X.dbf", "A/readme.txt"],
    )
    assert len(rows) == 1
    assert rows[0]["layer"] == "ST_20180508_WaterExtent_X" and rows[0]["source"] == "shp"


def test_rows_match_columns():
    for r in layers.layers_from_ogrinfo("s" * 64, "X.zip", INFO):
        assert list(r) == layers.LAYERS_COLUMNS


def test_layers_for_gdb_zip_without_gdb(tmp_path):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.shp", b"x")
    rows, status, error = layers.layers_for_gdb_zip("s" * 64, "x.zip", p)
    assert rows == [] and status == "no_layers" and error is None


def test_layers_for_gdb_zip_records_unreadable_zip(tmp_path):
    p = tmp_path / "not_a_zip.zip"
    p.write_bytes(b"this is not a zip file at all")
    rows, status, error = layers.layers_for_gdb_zip("s" * 64, "not_a_zip.zip", p)
    assert rows == []
    assert status == "zip_unreadable"
    assert "BadZipFile" in error


def test_layers_for_gdb_zip_records_unreadable_gdb(tmp_path, monkeypatch):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("X.gdb/junk.txt", b"not a real gdb")

    from gie.unosat import domains

    def fake_ogrinfo_json(path):
        raise domains.OgrinfoError(f"ogrinfo failed on {path}: boom")

    monkeypatch.setattr(domains, "ogrinfo_json", fake_ogrinfo_json)
    rows, status, error = layers.layers_for_gdb_zip("s" * 64, "x.zip", p)
    assert rows == []
    assert status == "gdb_unreadable"
    assert "X.gdb" in error


def test_layers_for_gdb_zip_keeps_rows_from_readable_gdb(tmp_path, monkeypatch):
    p = tmp_path / "multi.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("good.gdb/a.gdbtable", b"x")
        z.writestr("bad.gdb/a.gdbtable", b"x")

    from gie.unosat import domains

    def fake_ogrinfo_json(path):
        if path.name == "good.gdb":
            return INFO
        raise domains.OgrinfoError(f"ogrinfo failed on {path}: boom")

    monkeypatch.setattr(domains, "ogrinfo_json", fake_ogrinfo_json)
    rows, status, error = layers.layers_for_gdb_zip("s" * 64, "multi.zip", p)
    assert status == "gdb_unreadable"
    assert rows and rows[0]["zip_basename"] == "multi.zip"
    assert "bad.gdb" in error


def test_layers_for_gdb_zip_reports_nested_gdb_name(tmp_path, monkeypatch):
    p = tmp_path / "nested.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("sub/bad.gdb/a.gdbtable", b"x")

    from gie.unosat import domains

    def fake_ogrinfo_json(path):
        raise domains.OgrinfoError(f"ogrinfo failed on {path}: boom")

    monkeypatch.setattr(domains, "ogrinfo_json", fake_ogrinfo_json)
    rows, status, error = layers.layers_for_gdb_zip("s" * 64, "nested.zip", p)
    assert status == "gdb_unreadable"
    assert "sub/bad.gdb" in error


def test_layers_for_shp_zip_missing_from_inventory_is_recorded_not_raised():
    sha = "s" * 64
    rows, status, error = layers.layers_for_shp_zip(sha, "X_SHP.zip", set(), [])
    assert rows == []
    assert status == "missing_from_inventory"
    assert sha in error


def test_layers_for_shp_zip_present_with_shp_members_is_ok():
    sha = "s" * 64
    rows, status, error = layers.layers_for_shp_zip(
        sha, "X_SHP.zip", {sha}, ["a/b.shp", "a/b.dbf"]
    )
    assert status == "ok" and error is None
    assert len(rows) == 1 and rows[0]["layer"] == "b"


def test_layers_for_shp_zip_present_with_no_shp_members_is_no_layers():
    sha = "s" * 64
    rows, status, error = layers.layers_for_shp_zip(sha, "X.zip", {sha}, ["a/readme.txt"])
    assert rows == [] and status == "no_layers" and error is None


def test_load_frames_returns_typed_empty_frames_when_nothing_is_written_yet(tmp_path):
    rows, status = layers.load_frames(tmp_path)
    assert list(rows.columns) == layers.LAYERS_COLUMNS and len(rows) == 0
    assert list(status.columns) == layers.STATUS_COLUMNS and len(status) == 0


def test_merge_and_persist_frames_replace_rows_by_sha256(tmp_path):
    rows_df, status_df = layers.load_frames(tmp_path)
    sha = "a" * 64
    first_rows = layers.layers_from_ogrinfo(sha, "X.zip", INFO)
    rows_df, status_df = layers.merge_batch(
        rows_df, status_df, first_rows, [layers.status_row(sha, "ok")]
    )
    layers.persist_frames(tmp_path, rows_df, status_df)

    second_rows = layers.layers_from_zip_members(sha, "X.zip", ["a/b.shp"])
    rows_df, status_df = layers.merge_batch(
        rows_df, status_df, second_rows, [layers.status_row(sha, "ok")]
    )
    layers.persist_frames(tmp_path, rows_df, status_df)

    on_disk = pd.read_parquet(tmp_path / "layers.parquet")
    assert len(on_disk) == 1 and on_disk.iloc[0]["source"] == "shp"
    status = pd.read_parquet(tmp_path / "layers_status.parquet")
    assert len(status) == 1
