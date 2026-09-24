from datetime import date, datetime

import pandas as pd
import pytest

from gie.unosat.acquisition import resolve_acq
from gie.unosat.grammar import LayerName


def _name(dates: tuple[date, ...] = (), window: tuple[date, date] | None = None) -> LayerName:
    """A minimal LayerName carrying only what resolve_acq looks at; the other
    fields are irrelevant to acquisition resolution and filled with
    placeholders."""
    return LayerName(
        raw="placeholder",
        sensor=None,
        sensor_raw=None,
        dates=dates,
        window=window,
        kind="flood",
        table="observed_event",
        area="Area",
        malformed_tokens=(),
    )


def _series(*values) -> pd.Series:
    return pd.Series(list(values))


def test_no_date_anywhere_is_none():
    result = resolve_acq(_name(), _series(None, pd.NaT))
    assert result == {
        "acq_datetime": None,
        "acq_window_start": None,
        "acq_window_end": None,
        "acq_precision": "none",
        "acq_method": "none",
        "acq_conflict": False,
    }


def test_attribute_only_no_filename_date():
    result = resolve_acq(_name(), _series(pd.Timestamp("2020-03-05", tz="UTC")))
    assert result["acq_datetime"] == datetime(2020, 3, 5)
    assert result["acq_window_start"] is None and result["acq_window_end"] is None
    assert result["acq_precision"] == "date"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is False


def test_filename_only_single_date_no_attribute():
    result = resolve_acq(_name(dates=(date(2019, 3, 30),)), _series(None))
    assert result["acq_datetime"] == datetime(2019, 3, 30)
    assert result["acq_precision"] == "date"
    assert result["acq_method"] == "filename"
    assert result["acq_conflict"] is False


def test_filename_only_window_no_attribute_is_composite():
    # e.g. a MaximumFlood layer name carrying several aggregated dates with
    # no per-polygon sensor date attribute at all.
    result = resolve_acq(
        _name(
            dates=(date(2022, 4, 1), date(2022, 4, 24)),
            window=(date(2022, 4, 1), date(2022, 4, 24)),
        ),
        _series(None, None),
    )
    assert result["acq_datetime"] is None
    assert result["acq_window_start"] == datetime(2022, 4, 1)
    assert result["acq_window_end"] == datetime(2022, 4, 24)
    assert result["acq_precision"] == "window"
    assert result["acq_method"] == "window"
    assert result["acq_conflict"] is False


def test_single_filename_date_agrees_with_attribute():
    result = resolve_acq(
        _name(dates=(date(2021, 1, 1),)),
        _series(pd.Timestamp("2021-01-01")),
    )
    assert result["acq_datetime"] == datetime(2021, 1, 1)
    assert result["acq_precision"] == "date"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is False


def test_window_filename_contains_attribute_agrees():
    result = resolve_acq(
        _name(
            dates=(date(2021, 11, 19), date(2021, 11, 23)),
            window=(date(2021, 11, 19), date(2021, 11, 23)),
        ),
        _series(pd.Timestamp("2021-11-21", tz="UTC")),
    )
    assert result["acq_datetime"] is None
    assert result["acq_window_start"] == datetime(2021, 11, 19)
    assert result["acq_window_end"] == datetime(2021, 11, 23)
    assert result["acq_precision"] == "window"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is False


def test_window_filename_attribute_at_boundary_agrees():
    # Attribute equal to the window's own start/end bound is agreement, not
    # a conflict.
    result = resolve_acq(
        _name(
            dates=(date(2021, 11, 19), date(2021, 11, 23)),
            window=(date(2021, 11, 19), date(2021, 11, 23)),
        ),
        _series(pd.Timestamp("2021-11-19")),
    )
    assert result["acq_conflict"] is False
    assert result["acq_method"] == "attribute"
    assert result["acq_precision"] == "window"


def test_day_month_swap_disagreement_20200305_vs_20200503():
    # Real survey case: filename `20200305`, attribute `2020-05-03`.
    result = resolve_acq(
        _name(dates=(date(2020, 3, 5),)),
        _series(pd.Timestamp("2020-05-03", tz="UTC")),
    )
    assert result["acq_datetime"] is None
    assert result["acq_window_start"] == datetime(2020, 3, 5)
    assert result["acq_window_end"] == datetime(2020, 5, 3)
    assert result["acq_precision"] == "window"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is True


def test_disagreement_20180508_vs_20180504():
    # Real survey case: filename `20180508`, attribute `2018-05-04`.
    result = resolve_acq(
        _name(dates=(date(2018, 5, 8),)),
        _series(pd.Timestamp("2018-05-04")),
    )
    assert result["acq_window_start"] == datetime(2018, 5, 4)
    assert result["acq_window_end"] == datetime(2018, 5, 8)
    assert result["acq_precision"] == "window"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is True


def test_attribute_outside_filename_window_conflicts_and_widens():
    # Real survey case: filename window `20220401_20220424`, attribute
    # `2022-04-25` falls outside (after) the window -> conflict spanning
    # 04-01..04-25.
    result = resolve_acq(
        _name(
            dates=(date(2022, 4, 1), date(2022, 4, 24)),
            window=(date(2022, 4, 1), date(2022, 4, 24)),
        ),
        _series(pd.Timestamp("2022-04-25", tz="UTC")),
    )
    assert result["acq_datetime"] is None
    assert result["acq_window_start"] == datetime(2022, 4, 1)
    assert result["acq_window_end"] == datetime(2022, 4, 25)
    assert result["acq_precision"] == "window"
    assert result["acq_method"] == "attribute"
    assert result["acq_conflict"] is True


def test_attribute_before_filename_window_conflicts_and_widens():
    result = resolve_acq(
        _name(
            dates=(date(2022, 4, 5), date(2022, 4, 24)),
            window=(date(2022, 4, 5), date(2022, 4, 24)),
        ),
        _series(pd.Timestamp("2022-04-01")),
    )
    assert result["acq_window_start"] == datetime(2022, 4, 1)
    assert result["acq_window_end"] == datetime(2022, 4, 24)
    assert result["acq_conflict"] is True
    assert result["acq_method"] == "attribute"


def test_sensor_dates_naive_timestamp_treated_as_utc():
    result = resolve_acq(_name(), _series(pd.Timestamp("2020-01-15")))
    assert result["acq_datetime"] == datetime(2020, 1, 15)


def test_sensor_dates_plain_string():
    result = resolve_acq(_name(), _series("2020-01-15"))
    assert result["acq_datetime"] == datetime(2020, 1, 15)


def test_sensor_dates_ignores_missing_values_mixed_with_one_real_date():
    result = resolve_acq(
        _name(dates=(date(2020, 1, 15),)),
        _series(None, pd.NaT, pd.Timestamp("2020-01-15", tz="UTC"), None),
    )
    assert result["acq_conflict"] is False
    assert result["acq_method"] == "attribute"


def test_multiple_distinct_sensor_dates_raises_value_error():
    with pytest.raises(ValueError):
        resolve_acq(
            _name(dates=(date(2020, 1, 15),)),
            _series(pd.Timestamp("2020-01-15"), pd.Timestamp("2020-01-16")),
        )


def test_empty_sensor_dates_series_treated_as_no_attribute():
    result = resolve_acq(_name(dates=(date(2019, 3, 30),)), pd.Series([], dtype="object"))
    assert result["acq_method"] == "filename"
    assert result["acq_conflict"] is False
