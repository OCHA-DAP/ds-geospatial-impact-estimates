import pytest

from gie.unosat import classes

# Every value bound to Water_Class / Water_Class_1 (older domain), keyed by
# domain code, verified from the extracted domains (task context).
WATER_CLASS = {
    0: ("Preflood Water", "water_pre"),
    1: ("Flood Water", "flood"),
    2: ("Flood-Affected Land / Possible Flood water", "flood_possible"),
    3: ("Probable Flash Flood-Affected Land", "flood_possible"),
    4: ("Satellite Detected Water", "water"),
    6: ("Possible Saturated, wet Soil/ possible Flood Water", "flood_possible"),
    9: ("Aquaculture (Wet Rice)", "other_water"),
    11: ("Satellite Detected Waters", "water"),
    14: ("Tsunami-Affected Land", "other_water"),
    88: ("Swamp/Marsh/Mangrove", "other_water"),
    99: ("Maximum Flood Water Extent (Cumulative)", "aggregate_max"),
}

# Water_Class2 (newer domain), keyed by domain code.
WATER_CLASS2 = {
    0: ("Archive Water Extent / Pre-Flood Water", "water_pre"),
    1: ("Flood Water", "flood"),
    2: ("Satellite Detected Water / Possible Saturated Soil", "flood_possible"),
    3: ("Probable Flash Flood-Affected Land", "flood_possible"),
    4: ("Aquaculture", "other_water"),
    5: ("Possible Satuated, wet soil", "flood_possible"),  # domain typo: "Satuated"
    6: ("Tsunami-Affected Land", "other_water"),
    7: ("Maximum Satellite Observed Water (Cumulative)", "aggregate_max"),
    8: ("Swamp / Marsh / Mangrove", "other_water"),
    9: ("Snow Cover", "other_water"),
}

# Shapefile free text seen with no domain behind it (task context): includes
# a "Waster" typo for "Water" and text also present as a domain value.
SHAPEFILE_TEXT = {
    "Permanent Water": "water_pre",
    "Archive Waster Extent / Pre-Flood Water": "water_pre",  # shapefile typo: "Waster"
    "Satellite Detected Water / Possible Saturated Soil": "flood_possible",
}

ALL_TEXT_TO_KIND = (
    [(text, kind) for text, kind in WATER_CLASS.values()]
    + [(text, kind) for text, kind in WATER_CLASS2.values()]
    + list(SHAPEFILE_TEXT.items())
)


@pytest.mark.parametrize("text,kind", ALL_TEXT_TO_KIND)
def test_every_domain_and_shapefile_value_resolves_via_text(text, kind):
    resolved_kind, method = classes.resolve_class(text, domain_lookup=None, decoded_text=None)
    assert (resolved_kind, method) == (kind, "text")


@pytest.mark.parametrize("text,kind", ALL_TEXT_TO_KIND)
def test_normalise_text_is_stable_key_for_every_value(text, kind):
    normalised = classes.normalise_text(text)
    assert classes.CLASS_TEXT_TO_KIND[normalised] == kind


@pytest.mark.parametrize(
    "variant",
    [
        "  flood   water  ",
        "FLOOD WATER",
        "Flood Water",  # non-breaking space
        "flood water\t",
    ],
)
def test_normalise_text_collapses_whitespace_and_case_incl_unicode(variant):
    assert classes.normalise_text(variant) == classes.normalise_text("Flood Water")
    assert classes.CLASS_TEXT_TO_KIND[classes.normalise_text(variant)] == "flood"


@pytest.mark.parametrize("code,text_and_kind", WATER_CLASS.items())
def test_gdb_code_with_domain_resolves_via_water_class_domain(code, text_and_kind):
    text, kind = text_and_kind
    domain_lookup = {str(c): t for c, (t, _k) in WATER_CLASS.items()}
    resolved_kind, method = classes.resolve_class(
        code, domain_lookup=domain_lookup, decoded_text=None
    )
    assert (resolved_kind, method) == (kind, "domain")


@pytest.mark.parametrize("code,text_and_kind", WATER_CLASS2.items())
def test_gdb_code_with_domain_resolves_via_water_class2_domain(code, text_and_kind):
    text, kind = text_and_kind
    domain_lookup = {str(c): t for c, (t, _k) in WATER_CLASS2.items()}
    resolved_kind, method = classes.resolve_class(
        code, domain_lookup=domain_lookup, decoded_text=None
    )
    assert (resolved_kind, method) == (kind, "domain")


def test_code_with_no_domain_entry_is_unresolved_not_a_guess():
    domain_lookup = {"0": "Preflood Water"}
    assert classes.resolve_class(5, domain_lookup=domain_lookup, decoded_text=None) == (
        None,
        "unresolved_code",
    )


def test_code_lookup_coerces_numeric_types_to_domain_string_keys():
    domain_lookup = {"2": "Flood-Affected Land / Possible Flood water"}
    # int, numpy-style float-with-integer-value, and numeric string must all match
    assert classes.resolve_class(2, domain_lookup=domain_lookup, decoded_text=None) == (
        "flood_possible",
        "domain",
    )
    assert classes.resolve_class(2.0, domain_lookup=domain_lookup, decoded_text=None) == (
        "flood_possible",
        "domain",
    )
    assert classes.resolve_class("2", domain_lookup=domain_lookup, decoded_text=None) == (
        "flood_possible",
        "domain",
    )


def test_shp_text_with_no_domain_lookup_resolves_via_text():
    assert classes.resolve_class(
        "Flood Water", domain_lookup=None, decoded_text=None
    ) == ("flood", "text")


def test_decoded_column_beats_raw_code():
    domain_lookup = {"0": "Preflood Water"}
    # raw code says water_pre, but the decoded d_* column text disagrees and wins
    assert classes.resolve_class(
        0, domain_lookup=domain_lookup, decoded_text="Flood Water"
    ) == ("flood", "decoded_column")


def test_decoded_column_used_even_without_domain_lookup():
    assert classes.resolve_class(
        None, domain_lookup=None, decoded_text="Flood Water"
    ) == ("flood", "decoded_column")


@pytest.mark.parametrize(
    "record",
    [
        {"class": 0, "sensor": 0, "confidence": 0},
        {"class": None, "sensor": None, "confidence": None},
        {"class": 0, "sensor": None, "confidence": 0},
    ],
)
def test_is_unfilled_true_for_all_default_records(record):
    assert classes.is_unfilled(record) is True


@pytest.mark.parametrize(
    "record",
    [
        {"class": 1, "sensor": 0, "confidence": 0},
        {"class": 0, "sensor": 1, "confidence": 0},
        {"class": 0, "sensor": 0, "confidence": 1},
    ],
)
def test_is_unfilled_false_when_any_field_is_populated(record):
    assert classes.is_unfilled(record) is False


def test_final_kind_uses_layer_name_when_unfilled():
    assert classes.final_kind("flood", None, True) == ("flood", False)


def test_final_kind_uses_layer_name_when_polygon_kind_is_null_but_not_unfilled():
    # e.g. class_method == "unresolved_code": no polygon kind to compare against
    assert classes.final_kind("water", None, False) == ("water", False)


def test_final_kind_conflict_when_polygon_water_pre_inside_flood_layer():
    assert classes.final_kind("flood", "water_pre", False) == ("water_pre", True)


def test_final_kind_no_conflict_when_polygon_kind_matches_layer_name():
    assert classes.final_kind("flood", "flood", False) == ("flood", False)


def test_final_kind_uses_polygon_kind_when_layer_name_has_no_kind():
    assert classes.final_kind(None, "water_pre", False) == ("water_pre", False)


@pytest.mark.parametrize(
    "sensor,expected",
    [
        ("Sentinel-1", "sar"),
        ("RADARSAT-2", "sar"),
        ("RCM", "sar"),
        ("TerraSAR-X", "sar"),
        ("ICEYE", "sar"),
        ("COSMO-SkyMed", "sar"),
        ("Pleiades", "optical_vhr"),
        ("WorldView", "optical_vhr"),
        ("GeoEye-1", "optical_vhr"),
        ("SkySat", "optical_vhr"),
        ("Planet", "optical_vhr"),
        ("SPOT", "optical_vhr"),
        ("Kompsat", "optical_vhr"),
        ("Sentinel-2", "optical_hr"),
        ("Landsat", "optical_hr"),
        ("VIIRS", "optical_coarse"),
        ("MODIS", "optical_coarse"),
        ("Sentinel-3", "optical_coarse"),
        ("multiple", "multiple"),
        (None, "unknown"),
        ("SomethingUnheardOf", "unknown"),
    ],
)
def test_sensor_class(sensor, expected):
    assert classes.sensor_class(sensor) == expected
