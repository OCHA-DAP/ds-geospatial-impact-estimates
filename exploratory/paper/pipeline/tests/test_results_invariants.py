"""Invariants over artefacts/results.csv: relations that must hold between numbers computed by
different scripts or lenses. A failure here means two parts of the paper disagree."""
import os
import re
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "..", "..")
sys.path.insert(0, PAPER)

R = pd.read_csv(os.path.join(PAPER, "results.csv"))
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
RULES = [f"{k}-of-6" for k in range(1, 7)]


def W(region, lens, radius):
    m = (R.region == region) & (R.lens == lens) & ((R.radius == radius) if radius is not None else R.radius.isna())
    return R[m].pivot_table(index="predictor", columns="metric", values="value", aggfunc="first", dropna=False)


def test_bounds_ladder_is_monotone_per_product():
    b = W("core", "bounds", 10).loc[PRODUCTS]
    assert (b.P_floor <= b.P_grade).all() and (b.P_floor <= b.P_crowd).all()
    assert (b.P_grade <= b.P_upper).all() and (b.P_crowd <= b.P_upper).all()


def test_crowd_credit_agrees_between_bounds_and_dial_table():
    b = W("core", "bounds", 10).loc[PRODUCTS]
    c = W("core", "crowd", 10).loc[PRODUCTS]
    assert (b.P_crowd.round(3) == c.P_crowd.round(3)).all()
    assert (b.crowd_cov.round(2) == c.crowd_cov.round(2)).all()
    assert (c.crowd_cov <= 1).all()


def test_floor_precision_agrees_between_dial_table_and_bounds():
    p = W("core", "points", 10).loc[PRODUCTS]
    b = W("core", "bounds", 10).loc[PRODUCTS]
    assert (p.P.round(3) == b.P_floor.round(3)).all()


def test_k_of_6_precision_rises_and_recall_falls_with_k():
    for r in (10, 20, 30):
        p = W("core", "points", r).loc[RULES]
        assert (p.P.diff().dropna() >= 0).all(), f"precision not monotone at r={r}"
        assert (p.R.diff().dropna() <= 0).all(), f"recall not monotone at r={r}"
        assert (p.n_flags.diff().dropna() <= 0).all()


def test_bootstrap_point_estimates_equal_the_dial_table():
    p = W("core", "points", 10).loc[PRODUCTS + RULES]
    ci = W("core", "ci", 10).loc[PRODUCTS + RULES]
    assert (p.P.round(3) == ci.P.round(3)).all() and (p.R.round(3) == ci.R.round(3)).all()
    assert ((ci.P_lo <= ci.P) & (ci.P <= ci.P_hi)).all()


def test_as_delivered_precision_never_exceeds_core_precision():
    core = W("core", "points", 10).loc[PRODUCTS].P
    asd = W("asd", "points", 10).loc[PRODUCTS].P
    assert (asd <= core + 1e-9).all()


def test_flag_totals_are_at_least_in_extent_flags():
    t = W("all", "flags", None).loc[PRODUCTS]
    asd = W("asd", "points", 10).loc[PRODUCTS]
    assert (t.total_flags >= asd.n_flags).all()
    assert ((t.share_outside >= 0) & (t.share_outside <= 1)).all()


def test_every_key_the_brief_uses_exists():
    from brief_numbers import N
    qmd = open(os.path.join(PAPER, "manuscript_brief.qmd")).read()
    keys = set(re.findall(r'\{python\} N\["([^"]+)"\]', qmd))
    missing = [k for k in keys if k not in N]
    assert not missing, missing
