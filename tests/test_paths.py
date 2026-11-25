"""Regression guard: the path helpers must keep the VE tree byte-identical.

The VE event tree was copied to event= preserving its historical adm0= segment
(ADR-0027, as-built), and the un-evented legacy tree (event=None, App Service)
also carries adm0=. New events file directly under source= / model=common. A
change that breaks these invariants silently rewires what the VE viewer reads.
"""

from gie.config import Settings, common_segments, source_segments

VE = "20260624-ve-earthquake"
CO = "20260810-co-earthquake"
S = Settings(account_prefix="x")


def test_ve_source_paths_unchanged():
    assert source_segments("copernicus_ems", VE) == ["source=copernicus_ems", "adm0=VE"]
    assert (
        S.blob_path("silver", *source_segments("microsoft", VE), "footprints.parquet", event=VE)
        == "ds-geospatial-impact-estimates/silver/event=20260624-ve-earthquake/"
        "source=microsoft/adm0=VE/footprints.parquet"
    )


def test_co_source_paths_have_no_adm0():
    assert source_segments("copernicus_ems", CO) == ["source=copernicus_ems"]
    assert (
        S.blob_path("silver", *source_segments("microsoft", CO), "footprints.parquet", event=CO)
        == "ds-geospatial-impact-estimates/silver/event=20260810-co-earthquake/"
        "source=microsoft/footprints.parquet"
    )


def test_common_paths_ve_and_legacy_keep_adm0():
    assert common_segments(VE, "VE") == ["model=common", "adm0=VE"]
    assert common_segments(None, "VE") == ["model=common", "adm0=VE"]  # App Service legacy
    assert common_segments(CO, "CO") == ["model=common"]
