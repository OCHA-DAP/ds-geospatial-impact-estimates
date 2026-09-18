import shutil
import zipfile

import pandas as pd
import pytest

from gie.unosat import domains

INFO = {
    "layers": [
        {
            "name": "VIIRS_20211119_20211123_FloodExtent_SouthSudan",
            "fields": [
                {"name": "Water_Class", "domainName": "Water_Class2"},
                {"name": "Sensor_ID", "domainName": "SensorID_v2"},
                {"name": "Notes"},
            ],
        },
        {
            "name": "KS_20140505_Flood",
            "fields": [{"name": "Water_Class", "domainName": "Water_Class"}],
        },
        {
            "name": "Water_Class",
            "fields": [{"name": "Water_Class_code"}, {"name": "Water_Class_txt"}],
        },
    ],
    "domains": {
        "Water_Class": {
            "type": "coded",
            "codedValues": {"0": "Preflood Water", "1": "Flood Water"},
        },
        "Water_Class2": {
            "type": "coded",
            "codedValues": {
                "0": "Archive Water Extent / Pre-Flood Water",
                "2": "Satellite Detected Water / Possible Saturated Soil",
            },
        },
        "SensorID_v2": {"type": "coded", "codedValues": {"53": "VIIRS-NOAA"}},
        "Boolean": {"type": "coded", "codedValues": {"0": "No", "1": "Yes"}},
    },
}


def test_domain_rows_are_bound_per_layer_and_field():
    rows = domains.domain_rows("s" * 64, INFO)
    keyed = {(r["layer"], r["field"], r["code"]): r["value"] for r in rows}
    assert keyed[("VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Water_Class", "0")] == (
        "Archive Water Extent / Pre-Flood Water"
    )
    assert keyed[("KS_20140505_Flood", "Water_Class", "0")] == "Preflood Water"
    assert (
        keyed[("VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Sensor_ID", "53")]
        == "VIIRS-NOAA"
    )
    assert all(r["sha256"] == "s" * 64 for r in rows)
    # unbound fields and unused domains produce no rows
    assert not any(r["field"] == "Notes" for r in rows)
    assert not any(r["domain_name"] == "Boolean" for r in rows)


def test_domain_rows_empty_when_no_domains():
    info = {"layers": [{"name": "L", "fields": [{"name": "a"}]}]}
    assert domains.domain_rows("s" * 64, info) == []


def test_domains_for_gdb_zip_without_gdb(tmp_path):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.shp", b"x")
    rows, status, error = domains.domains_for_gdb_zip("s" * 64, p)
    assert rows == [] and status == "no_gdb_in_zip" and error is None


def test_ogrinfo_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))  # no ogrinfo here
    with pytest.raises(domains.OgrinfoError, match="ogrinfo"):
        domains.ogrinfo_json(tmp_path / "nothing.gdb")


def test_domains_for_gdb_zip_records_unreadable_gdb(tmp_path):
    if shutil.which("ogrinfo") is None:
        pytest.skip("ogrinfo not on PATH")
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("X.gdb/junk.txt", b"not a real gdb")
    rows, status, error = domains.domains_for_gdb_zip("s" * 64, p)
    assert rows == []
    assert status == "gdb_unreadable"
    assert "ogrinfo failed" in error


def test_domains_for_gdb_zip_records_unreadable_zip(tmp_path):
    p = tmp_path / "not_a_zip.zip"
    p.write_bytes(b"this is not a zip file at all")
    rows, status, error = domains.domains_for_gdb_zip("s" * 64, p)
    assert rows == []
    assert status == "zip_unreadable"
    assert "BadZipFile" in error


def test_ogrinfo_non_json_stdout_is_ogrinfo_error(monkeypatch, tmp_path):
    monkeypatch.setattr(domains.shutil, "which", lambda name: "/usr/bin/ogrinfo")

    class FakeProc:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(domains.subprocess, "run", lambda *a, **kw: FakeProc())
    with pytest.raises(domains.OgrinfoError, match="non-JSON"):
        domains.ogrinfo_json(tmp_path / "x.gdb")


def test_multi_gdb_zip_keeps_rows_from_readable_gdb(tmp_path, monkeypatch):
    p = tmp_path / "multi.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("good.gdb/a.gdbtable", b"x")
        z.writestr("bad.gdb/a.gdbtable", b"x")

    def fake_ogrinfo_json(path):
        if path.name == "good.gdb":
            return INFO
        raise domains.OgrinfoError(f"ogrinfo failed on {path}: boom")

    monkeypatch.setattr(domains, "ogrinfo_json", fake_ogrinfo_json)
    rows, status, error = domains.domains_for_gdb_zip("s" * 64, p)
    assert status == "gdb_unreadable"
    assert rows  # rows from the readable GDB are kept, not discarded
    assert "bad.gdb" in error


def test_persist_writes_typed_empty_rows_and_one_status_row(tmp_path):
    domains.persist(tmp_path, [], [domains.status_row("s" * 64, "no_domains", 0)])
    rows = pd.read_parquet(tmp_path / "domains.parquet")
    assert list(rows.columns) == ["sha256", "layer", "field", "domain_name", "code", "value"]
    assert len(rows) == 0
    status = pd.read_parquet(tmp_path / "domains_status.parquet")
    assert len(status) == 1


def test_persist_replaces_rows_for_same_sha256_rather_than_duplicating(tmp_path):
    sha = "s" * 64
    first = [
        {
            "sha256": sha,
            "layer": "L1",
            "field": "f1",
            "domain_name": "d1",
            "code": "0",
            "value": "a",
        }
    ]
    second = [
        {
            "sha256": sha,
            "layer": "L2",
            "field": "f2",
            "domain_name": "d2",
            "code": "1",
            "value": "b",
        },
        {
            "sha256": sha,
            "layer": "L2",
            "field": "f2",
            "domain_name": "d2",
            "code": "2",
            "value": "c",
        },
    ]
    domains.persist(tmp_path, first, [domains.status_row(sha, "ok", len(first))])
    domains.persist(tmp_path, second, [domains.status_row(sha, "ok", len(second))])
    rows = pd.read_parquet(tmp_path / "domains.parquet")
    assert len(rows) == len(second)
    assert set(rows["value"]) == {"b", "c"}
    status = pd.read_parquet(tmp_path / "domains_status.parquet")
    assert len(status) == 1


def test_persist_writes_rows_before_status(tmp_path, monkeypatch):
    calls = {"n": 0}
    original_to_parquet = pd.DataFrame.to_parquet

    def flaky_to_parquet(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash between rows and status writes")
        return original_to_parquet(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", flaky_to_parquet)
    with pytest.raises(RuntimeError, match="simulated crash"):
        domains.persist(tmp_path, [], [domains.status_row("s" * 64, "no_domains", 0)])
    assert (tmp_path / "domains.parquet").exists()
    assert not (tmp_path / "domains_status.parquet").exists()


def test_persist_accepts_legacy_status_file_without_error_column(tmp_path):
    legacy = pd.DataFrame(
        [
            {
                "sha256": "a" * 64,
                "status": "ok",
                "n_rows": 1,
                "processed_at": "2020-01-01T00:00:00+00:00",
            }
        ]
    )
    legacy.to_parquet(tmp_path / "domains_status.parquet")
    domains.persist(tmp_path, [], [domains.status_row("b" * 64, "no_domains", 0)])
    status = pd.read_parquet(tmp_path / "domains_status.parquet")
    assert len(status.columns) == 5
    assert len(status) == 2
