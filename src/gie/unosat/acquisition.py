"""Acquisition-date resolution for the UNOSAT flood archive (spec §3
"Acquisition").

Combines the date(s) parsed out of a layer name (`grammar.LayerName.dates` /
`.window`) with the per-polygon sensor date carried in the layer's own
attributes, and decides one acquisition datetime or window for the whole
layer, its precision, how it was derived, and whether the two sources
disagree.

Per-polygon sensor dates are reduced to a single value by the caller before
this module ever sees them: the silver builder (task 6) splits a layer by
distinct sensor date first, so `resolve_acq` only ever has to reconcile the
filename against *one* candidate attribute date. More than one distinct
non-null date in `sensor_dates` is therefore a caller bug, not an upstream
data state, and raises.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd

from gie.unosat.grammar import LayerName

__all__ = ["normalise_date", "resolve_acq"]


def normalise_date(value: object) -> date | None:
    """One raw per-polygon sensor-date value -> a naive-UTC `date`, or `None`
    for anything missing.

    Values arrive as tz-aware UTC `Timestamp`s from the GDB reader, naive
    `Timestamp`s or plain strings from the SHP reader, and `NaT`/`None` for
    polygons with no sensor date at all. A tz-aware value is converted to UTC
    before the time-of-day is dropped; a naive value is already treated as
    UTC (the spec: "UTC, naive"). UNOSAT never carries sub-day precision, so
    only the date component is kept.
    """
    if value is None or value is pd.NaT:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC")
    return ts.date()


def _resolve_attr_date(sensor_dates: pd.Series) -> date | None:
    """The single distinct non-null sensor date in `sensor_dates`, or `None`
    if every value is missing.

    Raises `ValueError` if more than one distinct date is present: the
    silver builder is responsible for splitting a layer by distinct sensor
    date before calling `resolve_acq`, so seeing several here means that
    split did not happen.
    """
    distinct = {d for d in (normalise_date(v) for v in sensor_dates) if d is not None}
    if len(distinct) > 1:
        raise ValueError(
            "resolve_acq received sensor_dates with more than one distinct date "
            f"({sorted(distinct)!r}); the caller must split the layer by distinct "
            "sensor date before calling resolve_acq"
        )
    return next(iter(distinct), None)


def _dt(d: date) -> datetime:
    """A `date` as a naive-UTC `datetime` at midnight (UNOSAT never gives
    minutes, so the time component is always zero)."""
    return datetime.combine(d, time.min)


def _result(
    acq_datetime: date | None,
    window_start: date | None,
    window_end: date | None,
    precision: str,
    method: str,
    conflict: bool,
) -> dict:
    return {
        "acq_datetime": _dt(acq_datetime) if acq_datetime is not None else None,
        "acq_window_start": _dt(window_start) if window_start is not None else None,
        "acq_window_end": _dt(window_end) if window_end is not None else None,
        "acq_precision": precision,
        "acq_method": method,
        "acq_conflict": conflict,
    }


def resolve_acq(name: LayerName, sensor_dates: pd.Series) -> dict:
    """Resolve one layer's acquisition date/window from its parsed name and
    its per-polygon sensor dates.

    Returns a dict with exactly the keys `acq_datetime, acq_window_start,
    acq_window_end, acq_precision, acq_method, acq_conflict`. Per spec §3
    "Acquisition":

    - No date anywhere -> `none`/`none`, everything else `None`/`False`.
    - Only the attribute carries a date -> `date`/`attribute`.
    - Only the filename carries a date: one date -> `date`/`filename`; a
      window (a composite layer's name carries several dates) ->
      `window`/`window`.
    - Filename date and attribute date agree (equal, or the attribute falls
      inside a filename window) -> `date`/`attribute` (single filename date)
      or `window`/`attribute` (filename window), `acq_conflict = False`.
    - They disagree -> `window`/`attribute` spanning both values (the
      filename window widened to include the attribute date, when the
      filename gave a window; otherwise the two single dates, sorted),
      `acq_conflict = True` — a consumer filtering to day precision drops
      these rather than silently trusting one source over the other.

    Note: the task brief glosses the filename-window-only case as
    `window`/`filename`; the spec's fuller acq_method description ties
    `filename` to a *single* filename date and reserves `method = window`
    for composites (a filename-only window), which is also the only way all
    four `acq_method` vocabulary values (`attribute`, `filename`, `window`,
    `none`) are ever produced. This module follows the spec.
    """
    attr_date = _resolve_attr_date(sensor_dates)
    filename_dates = name.dates
    window = name.window

    if not filename_dates:
        if attr_date is None:
            return _result(None, None, None, "none", "none", False)
        return _result(attr_date, None, None, "date", "attribute", False)

    if window is None:
        (fn_date,) = filename_dates
        if attr_date is None:
            return _result(fn_date, None, None, "date", "filename", False)
        if fn_date == attr_date:
            return _result(attr_date, None, None, "date", "attribute", False)
        start, end = sorted((fn_date, attr_date))
        return _result(None, start, end, "window", "attribute", True)

    w_start, w_end = window
    if attr_date is None:
        return _result(None, w_start, w_end, "window", "window", False)
    if w_start <= attr_date <= w_end:
        return _result(None, w_start, w_end, "window", "attribute", False)
    start = min(w_start, attr_date)
    end = max(w_end, attr_date)
    return _result(None, start, end, "window", "attribute", True)
