from datetime import date
from pathlib import Path

from gie.unosat import grammar


def P(n):
    return grammar.parse(n)


def test_simple_flood_extent():
    ln = P("VIIRS_20211119_20211123_FloodExtent_SouthSudan")
    assert ln.sensor == "VIIRS" and ln.window == (date(2021, 11, 19), date(2021, 11, 23))
    assert ln.kind == "flood" and ln.table == "observed_event" and ln.area == "SouthSudan"


def test_fused_sensor_date_and_underscore_kind():
    ln = P("ST20190330_Golestan_Flood_Water")
    assert ln.sensor == "Sentinel-1" and ln.dates == (date(2019, 3, 30),) and ln.kind == "flood"


def test_leading_unosat_and_multisensor():
    ln = P("UNOSAT_Multisensor_20260826_20260828_FloodExtent")
    assert (
        ln.sensor == "multiple"
        and ln.window == (date(2026, 8, 26), date(2026, 8, 28))
        and ln.kind == "flood"
    )


def test_multi_sensor_many_dates_is_window_min_max():
    ln = P(
        "ST3_20230606_20230607_20230609_ST2_20230608_ICEYE_20230607_FloodExtent_KhersonskaOblast"
    )
    assert (
        ln.sensor == "multiple"
        and ln.window == (date(2023, 6, 6), date(2023, 6, 9))
        and ln.kind == "flood"
    )


def test_precedence_preflood_and_maximum_before_flood():
    assert P("S1_20220224_PreFloodWaterExtent_Betroka").kind == "water_pre"
    assert P("VIIRS_20221224_20221228_MaximumFloodWaterExtent_SouthSudan").kind == "aggregate_max"
    assert P("S1_20230317_MinimumFloodWaterExtent_MWI").kind == "aggregate_min"
    assert P("RCM2_20220228_WaterExtent_Ifotaka").kind == "water"
    assert P("ST_20170302_Omusati_SatelliteDetectedSurfaceWater").kind == "water"


def test_coverage_and_skip():
    assert (
        P("RCM2_20220228_AnalysisExtent_Ifotaka").table == "coverage"
        and P("RCM2_20220228_AnalysisExtent_Ifotaka").kind == "footprint"
    )
    assert P("VIIRS_20190930_20191019_CloudObstruction_SouthSudan").kind == "not_analysed"
    assert P("WV3_20230607_AffectedHarbour_Kherson").kind == "skip"


def test_malformed_date_recorded_not_parsed():
    ln = P("RS2_0150118_Flood")
    assert ln.dates == () and ln.malformed_tokens == ("0150118",) and ln.kind == "flood"


def test_fixture_coverage_counts():
    fixtures = Path(__file__).parent / "fixtures"
    names = (fixtures / "layer_names_flood.txt").read_text().splitlines()
    parsed = [grammar.parse(n) for n in names]
    unmatched = [p.raw for p in parsed if p.kind is None]
    # <= 4 % unmatched and every unmatched name is listed in the fixture's sibling file
    assert len(unmatched) / len(names) <= 0.04, unmatched[:20]
    expected = set((fixtures / "layer_names_unmatched.txt").read_text().splitlines())
    assert set(unmatched) == expected
