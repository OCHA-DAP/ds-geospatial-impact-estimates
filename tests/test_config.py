import pytest

from gie.config import Settings


def test_event_path_inserted_after_tier_prefix():
    s = Settings()
    assert (
        s.blob_path("bronze", "source=x", "f.parquet", event="20260812-co-earthquake")
        == "ds-geospatial-impact-estimates/bronze/event=20260812-co-earthquake/source=x/f.parquet"
    )


def test_event_none_is_legacy_path():
    s = Settings()
    assert (
        s.blob_path("bronze", "source=codab", "adm0=CO", "adm1.parquet", event=None)
        == "ds-geospatial-impact-estimates/bronze/source=codab/adm0=CO/adm1.parquet"
    )


def test_event_omitted_is_a_typeerror():
    with pytest.raises(TypeError):
        Settings().blob_path("bronze", "source=x")


def test_prod_tier_suffix_composes_with_event():
    s = Settings(tier="prod")
    assert (
        s.blob_path("platinum", "meta", "sources.json", event="20260624-ve-earthquake")
        == "ds-geospatial-impact-estimates/platinum-prod/event=20260624-ve-earthquake/meta/sources.json"
    )
    # bronze/silver are untiered — event still applies
    assert s.blob_path("silver", "x.parquet", event="e1").startswith(
        "ds-geospatial-impact-estimates/silver/event=e1/"
    )


def test_az_path_wraps_blob_path():
    s = Settings()
    assert (
        s.az_path("gold", "facts.parquet", event="e1")
        == "az://projects/ds-geospatial-impact-estimates/gold/event=e1/facts.parquet"
    )
