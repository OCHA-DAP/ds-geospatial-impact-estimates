import zipfile

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
    rows, status = domains.domains_for_gdb_zip("s" * 64, p)
    assert rows == [] and status == "no_gdb_in_zip"


def test_ogrinfo_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))  # no ogrinfo here
    with pytest.raises(RuntimeError, match="ogrinfo"):
        domains.ogrinfo_json(tmp_path / "nothing.gdb")
