import pandas as pd

from gie.unosat import common, discovery

DS = {
    "id": "ds-1",
    "name": "satellite-detected-water-extents-south-sudan",
    "title": "Satellite detected water extents between 14 and 18 December 2024 over South Sudan",
    "dataset_date": "[2024-12-20T00:00:00 TO 2024-12-20T23:59:59]",
    "metadata_created": "2024-12-20T10:00:00.000000",
    "metadata_modified": "2024-12-21T10:00:00.000000",
    "license_id": "cc-by-sa",
    "groups": [{"title": "South Sudan", "name": "ssd"}],
    "tags": [{"name": "flooding"}, {"name": "geodata"}],
    "notes": "text",
    "methodology": "Other",
    "methodology_other": "SAR + VIIRS",
    "resources": [
        {
            "id": "r-shp", "name": "FL20220424SSD_SHP.zip", "format": "SHP",
            "url": "https://unosat.org/static/x/FL20220424SSD_SHP.zip",
            "size": 56726504, "hash": "abc", "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-gdb", "name": "FL20220424SSD_gdb.zip", "format": "Geodatabase",
            "url": "https://unosat-maps.web.cern.ch/SS/FL20220424SSD_gdb.zip",
            "size": 20680843, "hash": None, "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-kmz", "name": "FL20220424SSD.kmz", "format": "KMZ",
            "url": "https://unosat.org/static/x/FL20220424SSD.kmz",
            "size": 100, "hash": None, "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-xlsx", "name": "UNOSAT_PopulationExposure_SouthSudan.xlsx", "format": "XLSX",
            "url": "https://unosat.org/static/x/exposure.xlsx",
            "size": 38572, "hash": "def", "last_modified": "2024-12-20T09:00:00",
        },
    ],
}


def test_datasets_table_flattens_groups_tags_and_licence():
    t = discovery.datasets_table([DS])
    assert len(t) == 1
    row = t.iloc[0]
    assert row["countries"] == "South Sudan"
    assert row["tags"] == "flooding; geodata"
    assert row["licence"] == "cc-by-sa"
    assert row["n_resources"] == 4


def test_resources_ledger_one_row_per_resource_with_statuses():
    led = discovery.resources_ledger([DS])
    assert list(led.columns) == common.LEDGER_COLS
    assert len(led) == 4
    by = led.set_index("resource_id")
    assert by.loc["r-shp", "status"] == "pending"
    assert by.loc["r-gdb", "status"] == "pending"
    assert by.loc["r-xlsx", "status"] == "pending"
    assert by.loc["r-kmz", "status"] == "excluded_kmz"


def test_resources_ledger_parses_event_code_scope_and_host():
    by = discovery.resources_ledger([DS]).set_index("resource_id")
    assert by.loc["r-shp", "event_code"] == "FL20220424SSD"
    assert by.loc["r-shp", "hazard_prefix"] == "FL"
    assert by.loc["r-shp", "iso3"] == "SSD"
    assert by.loc["r-shp", "scope"] == "flood"
    assert by.loc["r-gdb", "host"] == "unosat-maps.web.cern.ch"
    assert pd.isna(by.loc["r-xlsx", "event_code"])
    assert by.loc["r-xlsx", "scope"] == "unknown"


def test_target_id_is_resource_version():
    by = discovery.resources_ledger([DS]).set_index("resource_id")
    assert by.loc["r-shp", "target_id"] == "r-shp@2024-12-20T09:00:00"


def test_merge_keeps_transfer_outcomes_and_flags_vanished():
    fresh = discovery.resources_ledger([DS])
    old = fresh.copy()
    old.loc[old.resource_id == "r-shp", ["status", "sha256", "size_bytes", "attempts"]] = [
        "uploaded", "f" * 64, 56726504, 1,
    ]
    gone = old.iloc[[0]].copy()
    gone["target_id"] = "r-old@2020-01-01T00:00:00"
    gone["resource_id"] = "r-old"
    gone["status"] = "uploaded"
    old = pd.concat([old, gone], ignore_index=True)

    merged = discovery.merge_ledgers(fresh, old).set_index("target_id")
    assert merged.loc["r-shp@2024-12-20T09:00:00", "status"] == "uploaded"
    assert merged.loc["r-shp@2024-12-20T09:00:00", "sha256"] == "f" * 64
    assert merged.loc["r-old@2020-01-01T00:00:00", "missing_upstream"]
    assert not merged.loc["r-gdb@2024-12-20T09:00:00", "missing_upstream"]


def test_merge_treats_new_version_as_new_row():
    fresh = discovery.resources_ledger([DS])
    old = fresh.copy()
    old["status"] = "uploaded"
    # upstream re-published r-shp with a new last_modified -> new target_id
    bumped = dict(DS)
    bumped["resources"] = [dict(DS["resources"][0], last_modified="2025-01-01T00:00:00")]
    fresh2 = discovery.resources_ledger([bumped])
    merged = discovery.merge_ledgers(fresh2, old)
    assert (merged.status == "pending").sum() == 1
    assert merged.loc[merged.status == "pending", "target_id"].item() == "r-shp@2025-01-01T00:00:00"
    assert merged.loc[merged.target_id == "r-shp@2024-12-20T09:00:00", "missing_upstream"].item()
