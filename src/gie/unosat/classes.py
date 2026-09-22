"""Water-class resolution and sensor class (spec §3 "Per-polygon class").

Pure, no I/O. Resolves a polygon's ``Water_Class`` value — a code bound to
one of the geodatabase's coded-value domains (per (layer, field), see
``domains.py``), or free text carried directly in a shapefile — to a
``layer_kind``, then combines that with the layer name's own kind
(``grammar.LayerName.kind``) per the spec's precedence. Also maps a raw
sensor label to the coarse ``sensor_class`` used in gold's ``label_index``.

Normalisation strategy (see ``normalise_text``): casefolding and whitespace
collapsing are handled generically, but the two known misspellings in the
corpus ("Satuated" for "Saturated", "Waster" for "Water") are letter-level
typos that no generic normalisation fixes — they are mapped explicitly as
their own keys in ``CLASS_TEXT_TO_KIND`` instead.
"""

from __future__ import annotations

CLASS_METHODS = ("domain", "text", "decoded_column", "layer_name", "unresolved_code")

# Every value bound to Water_Class / Water_Class_1 / Water_Class2 across the
# three domains, plus shapefile free text seen with no domain behind it
# (task context, verified from the extracted domains). Keys here are the
# literal resolved text, already casefolded and whitespace-normalised as
# `normalise_text` would produce; built into the real (normalised) lookup
# table below rather than relied on to be typed correctly by hand twice.
_RAW_CLASS_TEXT_TO_KIND: dict[str, str] = {
    # water_pre
    "preflood water": "water_pre",
    "archive water extent / pre-flood water": "water_pre",
    "permanent water": "water_pre",
    "archive waster extent / pre-flood water": "water_pre",  # shapefile typo: "Waster"
    # flood
    "flood water": "flood",
    # water
    "satellite detected water": "water",
    "satellite detected waters": "water",
    # flood_possible
    "flood-affected land / possible flood water": "flood_possible",
    "satellite detected water / possible saturated soil": "flood_possible",
    "possible saturated, wet soil/ possible flood water": "flood_possible",
    "possible satuated, wet soil": "flood_possible",  # domain typo: "Satuated"
    "probable flash flood-affected land": "flood_possible",
    # other_water
    "aquaculture (wet rice)": "other_water",
    "aquaculture": "other_water",
    "swamp/marsh/mangrove": "other_water",
    "swamp / marsh / mangrove": "other_water",
    "snow cover": "other_water",
    "tsunami-affected land": "other_water",
    # aggregate_max
    "maximum flood water extent (cumulative)": "aggregate_max",
    "maximum satellite observed water (cumulative)": "aggregate_max",
}


def normalise_text(s: str) -> str:
    """Casefold and collapse whitespace (any run, incl. unicode spaces like
    NBSP, and leading/trailing) to a single ordinary space. Punctuation
    (``/``, ``-``, ``,``, parens) is left as-is: it is part of what
    distinguishes some canonical keys (``swamp/marsh/mangrove`` vs
    ``swamp / marsh / mangrove`` are both real, separately-seen forms)."""
    return " ".join(s.strip().casefold().split())


CLASS_TEXT_TO_KIND: dict[str, str] = {
    normalise_text(text): kind for text, kind in _RAW_CLASS_TEXT_TO_KIND.items()
}


def _code_key(raw_value: object) -> str | None:
    """Coerce a domain code to the string form used as a ``domain_lookup``
    key (``domains.py`` stores codes as ``str(code)`` of an integer, e.g.
    "0", "2", "99"). Handles int, numpy-style numeric types, and integral
    floats (a nullable numeric column read back as float64) the same way;
    a genuinely non-numeric string is passed through stripped, and a NaN or
    ``None`` input has no code to look up."""
    if raw_value is None:
        return None
    try:
        return str(int(raw_value))
    except (TypeError, ValueError):
        pass
    try:
        as_float = float(raw_value)
    except (TypeError, ValueError):
        return str(raw_value).strip()
    if as_float != as_float:  # NaN
        return None
    return str(int(as_float)) if as_float.is_integer() else str(raw_value).strip()


def resolve_class(
    raw_value: object,
    *,
    domain_lookup: dict[str, str] | None,
    decoded_text: str | None,
) -> tuple[str | None, str]:
    """Resolve a polygon's water-class value to ``(layer_kind, class_method)``.

    Precedence: a decoded ``d_*`` column (``decoded_text``) beats the raw
    code or text; failing that, a GDB code is looked up in ``domain_lookup``
    (the (layer, field)-bound domain, built by the caller from
    ``domains.parquet``); failing that, ``raw_value`` is treated as
    shapefile free text. A code absent from its domain resolves to
    ``(None, "unresolved_code")`` rather than a guess — never silently
    dropped into some default kind.
    """
    if decoded_text is not None:
        normalised = normalise_text(decoded_text)
        if normalised:
            return CLASS_TEXT_TO_KIND.get(normalised), "decoded_column"

    if domain_lookup is not None:
        key = _code_key(raw_value)
        text = domain_lookup.get(key) if key is not None else None
        if text is None:
            return None, "unresolved_code"
        return CLASS_TEXT_TO_KIND.get(normalise_text(text)), "domain"

    if raw_value is None:
        return None, "unresolved_code"
    return CLASS_TEXT_TO_KIND.get(normalise_text(str(raw_value))), "text"


def is_unfilled(record: dict) -> bool:
    """True when ``class``, ``sensor`` and ``confidence`` are all 0 or None
    — an all-default record (a SHP export's zero-filled row, or a GDB row
    with every one of these attributes null)."""
    return all(record.get(k) in (0, None) for k in ("class", "sensor", "confidence"))


def final_kind(
    layer_kind_from_name: str | None,
    polygon_kind: str | None,
    unfilled: bool,
) -> tuple[str | None, bool]:
    """Combine the layer name's kind with the resolved per-polygon kind.

    The layer name decides when there is no usable polygon kind (null —
    e.g. ``unresolved_code`` — or an unfilled record). Otherwise the
    polygon kind wins; when it disagrees with the layer name's kind,
    ``class_conflict`` is set rather than silently preferring one side.
    Returns ``None`` only if neither side has a kind (e.g. an unclassified
    layer name whose polygon code also failed to resolve).
    """
    if polygon_kind is None or unfilled:
        return layer_kind_from_name, False
    if layer_kind_from_name is None:
        return polygon_kind, False
    return polygon_kind, polygon_kind != layer_kind_from_name


# (needle, sensor_class), checked as a casefolded substring against the
# sensor label — either `grammar.LayerName.sensor`'s canonical form
# (`grammar.SENSOR_ALIASES`' values) or a per-polygon Sensor_ID domain's
# decoded text, which can carry sensors the filename grammar never sees
# (COSMO-SkyMed, SkySat, SPOT, Kompsat). "multiple" is checked separately,
# as an exact match, since it names a fusion strategy, not a sensor family.
_SENSOR_CLASS_RULES: tuple[tuple[str, str], ...] = (
    ("sentinel-1", "sar"),
    ("radarsat", "sar"),
    ("rcm", "sar"),
    ("terrasar", "sar"),
    ("iceye", "sar"),
    ("cosmo", "sar"),
    ("sentinel-2", "optical_hr"),
    ("landsat", "optical_hr"),
    ("sentinel-3", "optical_coarse"),
    ("viirs", "optical_coarse"),
    ("modis", "optical_coarse"),
    ("pleiades", "optical_vhr"),
    ("worldview", "optical_vhr"),
    ("geoeye", "optical_vhr"),
    ("skysat", "optical_vhr"),
    ("planet", "optical_vhr"),
    ("spot", "optical_vhr"),
    ("kompsat", "optical_vhr"),
)


def sensor_class(sensor: str | None) -> str:
    if sensor is None:
        return "unknown"
    folded = sensor.casefold()
    if folded == "multiple":
        return "multiple"
    for needle, cls in _SENSOR_CLASS_RULES:
        if needle in folded:
            return cls
    return "unknown"
