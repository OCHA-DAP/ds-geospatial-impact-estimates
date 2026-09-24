"""Gold v3 PoC: burning label sets instead of dissolving them (ADR-0037)."""

import importlib.util
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box

_POC = Path(__file__).resolve().parents[2] / "pipelines" / "unosat" / "gold_raster_poc.py"
spec = importlib.util.spec_from_file_location("gold_raster_poc", _POC)
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


def test_grid_window_is_snapped_to_the_global_30_arcsec_grid():
    transform, h, w = poc.grid_for((10.004, 20.001, 10.02, 20.03))
    # origin sits on a global cell corner: multiples of 1/120 from (-180, 90)
    assert abs(((transform.c + 180) / poc.RES) - round((transform.c + 180) / poc.RES)) < 1e-9
    assert abs(((90 - transform.f) / poc.RES) - round((90 - transform.f) / poc.RES)) < 1e-9
    assert h >= 4 and w >= 2


def test_burn_is_a_logical_or_so_overlaps_do_not_matter():
    transform, h, w = poc.grid_for((0, 0, 1, 1))
    a = box(0, 0, 0.5, 1)
    b = box(0.25, 0, 1, 1)  # overlaps a
    both = poc.burn([a, b], transform, h, w)
    union = poc.burn([a.union(b)], transform, h, w)
    assert both.sum() > 0
    assert np.array_equal(both, union)


def test_burn_accepts_an_invalid_bowtie_without_repair():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert not bowtie.is_valid
    transform, h, w = poc.grid_for((0, 0, 1, 1))
    out = poc.burn([bowtie], transform, h, w)
    assert out.sum() > 0  # scanline fill, no GEOS validity required


def test_valid_mask_is_footprint_and_not_cloud():
    import geopandas as gpd

    transform, h, w = poc.grid_for((0, 0, 1, 1))
    foot = gpd.GeoDataFrame({"role": ["footprint"]}, geometry=[box(0, 0, 1, 1)], crs=4326)
    cloud = gpd.GeoDataFrame({"role": ["not_analysed"]}, geometry=[box(0, 0, 0.5, 1)], crs=4326)
    group = gpd.GeoDataFrame({"layer_kind": ["flood"]}, geometry=[box(0.6, 0, 0.9, 1)], crs=4326)
    bands = poc.rasterise_label_set(group, foot, cloud, transform, h, w)
    assert 0 < bands["valid"].sum() < h * w
    # the clouded half is unobserved even where nothing is flooded
    assert bands["valid"][:, : w // 4].sum() == 0
    assert (
        bands["water"].sum() > 0 and (bands["water"] & bands["valid"]).sum() == bands["water"].sum()
    )
