"""Layer-name grammar for the UNOSAT flood/cyclone archive.

Pure parsing, no I/O: tokenises a layer name on ``_`` and classifies it into
sensor, acquisition date(s), a ``layer_kind`` (or coverage role, or a skip
class for non-water impact/admin layers), and an area label. See
``docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md`` §3
"Layer grammar" for the vocabulary and precedence this implements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

_FUSED_SENSOR_DATE = re.compile(r"([A-Za-z]+)(\d{8})")

# Sensor prefix -> normalised name (spec §3 / brief). An unrecognised leading
# alphabetic token is kept verbatim as `sensor_raw` with `sensor=None` rather
# than guessed.
SENSOR_ALIASES: dict[str, str] = {
    "ST": "Sentinel-1",
    "ST1": "Sentinel-1",
    "S1": "Sentinel-1",
    "ST2": "Sentinel-2",
    "S2": "Sentinel-2",
    "ST3": "Sentinel-3",
    "S3": "Sentinel-3",
    "PHR": "Pleiades",
    "PL": "Planet",
    "PLANETSCOPE": "Planet",
    "PT": "Planet",
    "RS": "RADARSAT-2",
    "RS2": "RADARSAT-2",
    "RCM": "RCM",
    "RCM1": "RCM",
    "RCM2": "RCM",
    "WV": "WorldView",
    "WV1": "WorldView",
    "WV2": "WorldView",
    "WV3": "WorldView",
    "WV03": "WorldView",
    "L8": "Landsat",
    "LS8": "Landsat",
    "L9": "Landsat",
    "LS": "Landsat",
    "TSX": "TerraSAR-X",
    "TX": "TerraSAR-X",
    "TDX": "TerraSAR-X",
    "GE01": "GeoEye-1",
    "VIIRS": "VIIRS",
    "MODIS": "MODIS",
    "ICEYE": "ICEYE",
    "MULTISENSOR": "multiple",
    "MULTISENSORS": "multiple",
    "MULTI": "multiple",
}

# Impact / admin / infrastructure layers: checked before every kind needle
# below, so e.g. "FloodedCropland" (a crop-damage layer, not the event's
# water extent -- that lives in a sibling "FloodExtent" layer) is `skip`
# rather than `flood`. `cropland` and `waterway` are not in the spec §3
# table; added because the final 2,772-name fixture (final for this repo,
# spec table analysis predates it) carries "PotentiallyAffectedCropland" /
# "FloodedCropland" / "Waterways_AOI…" layers that are impact or reference
# layers, not primary water/flood extents -- see task-2-report.md.
SKIP_NEEDLES: tuple[str, ...] = (
    "damage",
    "structure",
    "building",
    "idp",
    "shelter",
    "landslide",
    "road",
    "bridge",
    "harbour",
    "health",
    "cropland",
    "waterway",
)

# (needle, table, kind) in precedence order exactly as spec §3's grammar
# table (PreFlood/Maximum/Minimum before Flood; CloudObstruction/AnalysisExtent
# before Water/Extent).
KIND_RULES: tuple[tuple[str, str, str], ...] = (
    ("cloudobstruction", "coverage", "not_analysed"),
    # underscore variant, same reasoning as analysisextent/analysis_extent
    # below: real names split it across two tokens ("Cloud_Obstruction");
    # unlike flood/water there is no bare "cloud" or "obstruction" fallback
    # needle to catch these otherwise, so they were landing unclassified.
    ("cloud_obstruction", "coverage", "not_analysed"),
    ("analysisextent", "coverage", "footprint"),
    ("analysis_extent", "coverage", "footprint"),
    ("areaofinterest", "coverage", "footprint"),
    ("aoi", "coverage", "footprint"),
    ("permanentwater", "observed_event", "water_pre"),
    ("prefloodwater", "observed_event", "water_pre"),
    ("preflood", "observed_event", "water_pre"),
    ("archivewater", "observed_event", "water_pre"),
    ("maximumflood", "observed_event", "aggregate_max"),
    ("maxflood", "observed_event", "aggregate_max"),
    ("cumulative", "observed_event", "aggregate_max"),
    ("minimumflood", "observed_event", "aggregate_min"),
    ("floodextent", "observed_event", "flood"),
    ("flood_water", "observed_event", "flood"),
    ("floodwater", "observed_event", "flood"),
    ("flood", "observed_event", "flood"),
    ("satellitedetectedsurfacewater", "observed_event", "water"),
    ("satellitedetectedwater", "observed_event", "water"),
    ("waterextent", "observed_event", "water"),
    ("water", "observed_event", "water"),
    ("extent", "coverage", "footprint"),
)

# "aoi" (and its spelled-out form) must match a whole token, never a raw
# substring: dozens of real names append a numbered zone like "_AOI5" after
# a genuine kind ("ST1_20191105_WaterExtent_BasseKotto_CAF_AOI1"), and since
# this rule sits ahead of the water/flood groups in the precedence table, a
# substring match on "aoi" would misclassify every one of those real water
# layers as a coverage footprint instead. Plain substring matching is kept
# for the standalone-token cases ("AOI_UNOSAT", "Dominica_AOIs_Copernicus").
_TOKEN_EXACT_NEEDLES = frozenset({"aoi", "areaofinterest"})


@dataclass(frozen=True)
class LayerName:
    raw: str
    sensor: str | None
    sensor_raw: str | None
    dates: tuple[date, ...]
    window: tuple[date, date] | None
    kind: str | None
    table: str | None
    area: str
    malformed_tokens: tuple[str, ...]


def _valid_date(token: str) -> date | None:
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        return datetime.strptime(token, "%Y%m%d").date()
    except ValueError:
        return None


def _match_kind(
    folded: str, tokens_folded: list[str]
) -> tuple[str | None, str | None, str | None]:
    """Return (needle, table, kind) for the first precedence match, or all-None."""
    for needle in SKIP_NEEDLES:
        if needle in folded:
            return needle, None, "skip"
    for needle, table, kind in KIND_RULES:
        if needle in _TOKEN_EXACT_NEEDLES:
            if any(t == needle or t == needle + "s" for t in tokens_folded):
                return needle, table, kind
            continue
        if needle in folded:
            return needle, table, kind
    return None, None, None


def parse(name: str) -> LayerName:
    tokens = [t for t in name.split("_") if t]
    if tokens and tokens[0].upper() == "UNOSAT":
        tokens = tokens[1:]

    needle, table, kind = _match_kind(name.casefold(), [t.casefold() for t in tokens])

    dates: list[date] = []
    malformed: list[str] = []
    # Ordered pieces feed both sensor detection and area assembly; a fused
    # sensor+date token ("ST20190330") expands to a word piece (the sensor
    # prefix) followed by a date piece, preserving position.
    pieces: list[tuple[str, str]] = []
    for token in tokens:
        if token.isdigit():
            parsed = _valid_date(token)
            if parsed is not None:
                dates.append(parsed)
                pieces.append(("date", token))
            else:
                malformed.append(token)
            continue
        fused = _FUSED_SENSOR_DATE.fullmatch(token)
        if fused:
            prefix, digits = fused.groups()
            parsed = _valid_date(digits)
            if parsed is not None:
                dates.append(parsed)
                pieces.append(("word", prefix))
                pieces.append(("date", digits))
                continue
            malformed.append(token)
            continue
        pieces.append(("word", token))

    # Sensor: consecutive recognised sensor tokens from the start of the
    # name; the scan stops at the first word token that isn't a known alias
    # (an area/place token, or the kind token itself). More than one
    # recognised sensor token before that point means a fused/multi-sensor
    # name ("ST3_..._ST2_..._ICEYE_..._FloodExtent") -> sensor = "multiple".
    # An unrecognised *first* word token is kept as `sensor_raw` (and, like
    # a resolved sensor, excluded from `area`) rather than left to appear in
    # both fields; an unrecognised word appearing after an already-resolved
    # sensor is ordinary area text.
    sensor_aliases_seen: list[str] = []
    first_unrecognised: str | None = None
    area_start = len(pieces)
    for i, (ptype, value) in enumerate(pieces):
        if ptype == "date":
            continue
        alias = SENSOR_ALIASES.get(value.upper())
        if alias is not None:
            sensor_aliases_seen.append(alias)
            continue
        if not sensor_aliases_seen:
            first_unrecognised = value
            area_start = i + 1
        else:
            area_start = i
        break
    else:
        area_start = len(pieces)

    sensor: str | None
    sensor_raw: str | None
    if not sensor_aliases_seen:
        sensor = None
        sensor_raw = first_unrecognised
    elif "multiple" in sensor_aliases_seen or len(sensor_aliases_seen) > 1:
        sensor = "multiple"
        sensor_raw = None
    else:
        sensor = sensor_aliases_seen[0]
        sensor_raw = None

    # Area: word tokens after the sensor zone, excluding whichever token(s)
    # supplied the matched needle (needles with an underscore, e.g.
    # "flood_water", can span two tokens).
    needle_parts = needle.split("_") if needle else []
    area_tokens = [
        value
        for ptype, value in pieces[area_start:]
        if ptype == "word"
        and not (needle_parts and any(part in value.casefold() for part in needle_parts))
    ]
    area = "_".join(area_tokens)

    window = (min(dates), max(dates)) if len(dates) >= 2 else None

    return LayerName(
        raw=name,
        sensor=sensor,
        sensor_raw=sensor_raw,
        dates=tuple(dates),
        window=window,
        kind=kind,
        table=table,
        area=area,
        malformed_tokens=tuple(malformed),
    )
