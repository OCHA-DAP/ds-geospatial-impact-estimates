"""Synthetic-geometry tests for the paper's shared definitions (no data access)."""
import os
import sys

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, box

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paperlib as pl  # noqa: E402

CRS = pl.METRIC_CRS


def gdf(geoms):
    return gpd.GeoDataFrame(geometry=list(geoms), crs=CRS)


def test_polygon_distance_credits_a_point_on_the_footprint_edge():
    # a 30 m x 10 m building; the reference point sits on its far end, 15 m from the centre
    bld = gdf([box(0, 0, 30, 10)])
    ref = gdf([Point(30, 5)])
    s = pl.score(bld, ref, r=10)
    assert s["P"] == 1.0 and s["R"] == 1.0            # footprint frame: a hit
    cen = gdf([b.centroid for b in bld.geometry])
    assert pl.score(cen, ref, r=10)["P"] == 0.0        # centroid frame would have missed it


def test_score_is_dual_anchored():
    # two flagged buildings, one reference point near the first: P = 1/2, R = 1
    bld = gdf([box(0, 0, 10, 10), box(100, 0, 110, 10)])
    ref = gdf([Point(5, 12)])
    s = pl.score(bld, ref, r=10)
    assert (s["P"], s["R"], s["n_flags"], s["n_ref"]) == (0.5, 1.0, 2, 1)


def test_predictors_include_products_pairs_and_rules():
    import pandas as pd
    b = pd.DataFrame({c: [1, 0, 1] for c in pl.PRODUCTS.values()})
    b["ms_dmg"] = [1, 1, 0]
    b["votes"] = b[list(pl.PRODUCTS.values())].sum(axis=1)
    p = pl.predictors(b)
    assert set(p) == set(pl.PRODUCTS) | {f"{a}∧{c}" for a, c in pl.PAIRS} | {f"{k}-of-6" for k in range(1, 7)}
    assert list(p["6-of-6"]) == [True, False, False]
    assert list(p["1-of-6"]) == [True, True, True]
    assert list(p["MS∧UH"]) == [True, False, False]


def test_location_is_inside_the_footprint():
    # an L-shaped building whose centroid falls outside it
    from shapely.geometry import Polygon
    L = Polygon([(0, 0), (30, 0), (30, 5), (5, 5), (5, 30), (0, 30)])
    g = gdf([L])
    assert not L.contains(L.centroid)
    assert L.contains(pl.location(g).iloc[0])


def test_measured_crowd_credit_ignores_unreviewed_flags(monkeypatch):
    # three unmatched flags: reviewed-damaged, reviewed-undamaged, never reviewed
    bld = gdf([box(0, 0, 10, 10), box(100, 0, 110, 10), box(200, 0, 210, 10), box(300, 0, 310, 10)])
    ref = gdf([Point(305, 5)])                          # only the 4th building is a CEMS hit
    monkeypatch.setattr(pl, "crowd_verdicts", lambda g: np.array([1.0, 0.0, np.nan]))
    c = pl.crowd_credit(bld, ref, r=10)
    assert c["P_crowd"] == pytest.approx((1 + 1) / 4)   # hit + one confirmed; the unreviewed one earns nothing
    assert c["crowd_cov"] == pytest.approx(2 / 3)
    assert c["fp_crowd_damaged"] == pytest.approx(1 / 2)
