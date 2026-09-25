"""The flood-label platinum builder: two gold schemas in, one display product out.

What these verify and why it matters:
* the index harmonisation never invents a value (CEMS gets null sensor_class /
  water area, not a guess) and never drops a row silently (a UNOSAT name with
  no HDX record raises instead of a blank country);
* the geometry selection draws exactly what each source mapped: a null UNOSAT
  flood yields no flood row, an empty one neither, and both are counted as
  absent rather than vanishing;
* a label set the index does not know is an error, not an unlabeled shape.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from gie.flood_labels import platinum as P

T0 = pd.Timestamp("2022-08-11")
T1 = pd.Timestamp("2022-08-19")


def _cems_index() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code": ["EMSR001", "EMSR001"],
            "name": ["Flood in X", "Flood in X"],
            "countries": ["Sweden", "Sweden"],
            "aoi": ["AOI01", "AOI01"],
            "acq_start": [T0, T1],
            "acq_end": [T0, T1],
            "label_day": ["2022-08-11", "2022-08-19"],
            "sensor": ["Sentinel-1", None],
            "acq_method": ["source_table", "window"],
            "acq_precision": ["minute", "window"],
            "area_km2": [12.5, 3.0],
            "valid_basis": ["footprint_x_aoi", "aoi"],
            "minx": [0.0, 0.0],
            "miny": [0.0, 0.0],
            "maxx": [1.0, 1.0],
            "maxy": [1.0, 1.0],
        }
    )


def _unosat_index() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "label_source": ["unosat"] * 3,
            "code": ["FL20220728NER"] * 3,
            "name": ["geodata-niger"] * 3,
            "countries": ["NER"] * 3,
            "aoi": ["Tillaberi", "Tillaberi", ""],
            "acq_start": [T0, T1, T1],
            "acq_end": [T0, T1, T1],
            "label_day": ["2022-08-11", "2022-08-19", "2022-08-19"],
            "sensor": ["Sentinel-1", "VIIRS", "Sentinel-2"],
            "sensor_class": ["sar", "optical_coarse", "optical_hr"],
            "acq_method": ["attribute", "filename", "filename"],
            "acq_precision": ["date", "date", "date"],
            "water_area_km2": [5.0, 6.0, 7.0],
            "flood_area_km2": [1.0, np.nan, 0.0],
            "valid_basis": ["footprint", "none", "none"],
            "minx": [0.0] * 3,
            "miny": [0.0] * 3,
            "maxx": [1.0] * 3,
            "maxy": [1.0] * 3,
        }
    )


def _hdx() -> pd.DataFrame:
    return pd.DataFrame({"dataset_name": ["geodata-niger"], "countries": ["Niger"]})


# --- index -----------------------------------------------------------------


def test_cems_index_is_flood_only_with_nothing_invented():
    out = P.harmonise_index("cems", _cems_index())
    assert list(out.columns) == P.INDEX_COLS
    assert (out.label_source == "cems").all()
    assert out.sensor_class.isna().all()
    assert out.water_area_km2.isna().all()
    assert out.flood_area_km2.tolist() == [12.5, 3.0]
    assert str(out.acq_start.dtype) == "datetime64[us]"


def test_unosat_index_resolves_country_names_from_hdx():
    out = P.harmonise_index("unosat", _unosat_index(), _hdx())
    assert out.countries.tolist() == ["Niger"] * 3
    assert out.sensor_class.tolist() == ["sar", "optical_coarse", "optical_hr"]
    assert out.aoi.tolist() == ["Tillaberi", "Tillaberi", ""]


def test_unosat_name_without_hdx_record_raises():
    hdx = pd.DataFrame({"dataset_name": ["other"], "countries": ["Chad"]})
    with pytest.raises(KeyError, match="no HDX dataset record"):
        P.harmonise_index("unosat", _unosat_index(), hdx)


def test_unosat_index_without_hdx_table_raises():
    with pytest.raises(ValueError, match="hdx_datasets"):
        P.harmonise_index("unosat", _unosat_index())


def test_foreign_label_source_in_unosat_index_raises():
    idx = _unosat_index()
    idx.loc[0, "label_source"] = "cems"
    with pytest.raises(ValueError, match="label_source"):
        P.harmonise_index("unosat", idx, _hdx())


def test_missing_index_column_is_named():
    with pytest.raises(KeyError, match="area_km2"):
        P.harmonise_index("cems", _cems_index().drop(columns=["area_km2"]))


def test_unknown_source_raises():
    with pytest.raises(ValueError, match="unknown label source"):
        P.harmonise_index("gfm", _cems_index())


def test_combine_index_rejects_duplicate_display_key():
    c = P.harmonise_index("cems", _cems_index())
    with pytest.raises(ValueError, match="share a display key"):
        P.combine_index([c, c])


def test_combine_index_keeps_both_sources():
    out = P.combine_index(
        [
            P.harmonise_index("cems", _cems_index()),
            P.harmonise_index("unosat", _unosat_index(), _hdx()),
        ]
    )
    assert out.label_source.value_counts().to_dict() == {"unosat": 3, "cems": 2}


# --- display rows ------------------------------------------------------------


def _unosat_labels_file(tmp_path):
    sq = box(0, 0, 0.5, 0.5)
    g = gpd.GeoDataFrame(
        {
            "label_source": ["unosat"] * 3,
            "code": ["FL20220728NER"] * 3,
            "aoi": ["Tillaberi", "Tillaberi", ""],
            "acq_start": [T0, T1, T1],
            "acq_end": [T0, T1, T1],
            "label_day": ["2022-08-11", "2022-08-19", "2022-08-19"],
            "valid_basis": ["footprint", "none", "none"],
            "valid_match": ["product", None, None],
            "geom_water": gpd.GeoSeries([sq, sq, sq], crs="EPSG:4326"),
            # separated flood / never separated (null) / looked and found none (empty)
            "geom_flood": gpd.GeoSeries([box(0, 0, 0.2, 0.2), None, Polygon()], crs="EPSG:4326"),
            "geom_possible": gpd.GeoSeries([None, None, None], crs="EPSG:4326"),
            "geom_valid": gpd.GeoSeries([box(-1, -1, 2, 2), None, None], crs="EPSG:4326"),
        },
        geometry="geom_water",
        crs="EPSG:4326",
    )
    p = tmp_path / "unosat.parquet"
    g.to_parquet(p)
    return p


def test_unosat_rows_draw_what_the_source_mapped(tmp_path):
    index = P.combine_index([P.harmonise_index("unosat", _unosat_index(), _hdx())])
    rows, counts = P.display_rows("unosat", _unosat_labels_file(tmp_path), index)
    assert len(rows["water"]) == 3
    assert len(rows["flood"]) == 1, "null and empty flood geometries draw nothing"
    assert len(rows["masks"]) == 1
    assert counts == {"water_absent": 0, "flood_absent": 2, "masks_absent": 2}
    w = rows["water"][0]
    assert w["label_source"] == "unosat"
    assert w["sensor_class"] == "sar"
    assert w["area_km2"] == 5.0
    assert w["acq_start"] == "2022-08-11 00:00:00"
    assert rows["flood"][0]["area_km2"] == 1.0
    assert rows["masks"][0]["valid_basis"] == "footprint"
    assert "area_km2" not in rows["masks"][0]


def _cems_labels_file(tmp_path):
    g = gpd.GeoDataFrame(
        {
            "code": ["EMSR001", "EMSR001"],
            "aoi": ["AOI01", "AOI01"],
            "acq_start": [T0, T1],
            "acq_end": [T0, T1],
            "label_day": ["2022-08-11", "2022-08-19"],
            "geometry": gpd.GeoSeries([box(0, 0, 0.5, 0.5), box(0, 0, 0.1, 0.1)], crs="EPSG:4326"),
            "valid_geometry": gpd.GeoSeries([box(-1, -1, 2, 2), None], crs="EPSG:4326"),
            "valid_basis": ["footprint_x_aoi", "aoi"],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    p = tmp_path / "cems.parquet"
    g.to_parquet(p)
    return p


def test_cems_rows_are_flood_and_mask_only(tmp_path):
    index = P.combine_index([P.harmonise_index("cems", _cems_index())])
    rows, counts = P.display_rows("cems", _cems_labels_file(tmp_path), index)
    assert rows["water"] == []
    assert [r["area_km2"] for r in rows["flood"]] == [12.5, 3.0]
    assert rows["flood"][1]["sensor"] is None
    assert rows["flood"][0]["sensor_class"] is None
    assert len(rows["masks"]) == 1
    assert counts == {"flood_absent": 0, "masks_absent": 1}


def test_label_row_unknown_to_index_raises(tmp_path):
    index = P.combine_index([P.harmonise_index("cems", _cems_index().iloc[:1])])
    with pytest.raises(ValueError, match="no index row"):
        P.display_rows("cems", _cems_labels_file(tmp_path), index)


# --- simplify ----------------------------------------------------------------


def test_simplify_reduces_vertices_but_never_collapses_to_nothing():
    theta = np.linspace(0, 2 * np.pi, 2000, endpoint=False)
    circle = Polygon(np.c_[np.cos(theta), np.sin(theta)])
    out = P.simplify(circle, 1e-2)
    assert 0 < len(out.exterior.coords) < len(circle.exterior.coords)
    tiny = box(0, 0, 1e-6, 1e-6)
    assert P.simplify(tiny, 1e-3).equals(tiny), "a label set never vanishes"
    from shapely.geometry import MultiPolygon

    mixed = P.simplify(MultiPolygon([box(0, 0, 1, 1), tiny]), 1e-3)
    assert mixed.geom_type == "Polygon" and mixed.equals(box(0, 0, 1, 1)), (
        "a sub-tolerance part beside a drawable one is left out"
    )


def test_labels_file_under_hive_style_code_directory_reads(tmp_path):
    """Gold files live under `code={EventCode}/` and carry a `code` column;
    dataset-style readers refuse that combination (the trap the UNOSAT README
    documents). The reader must open the single file."""
    src = _cems_labels_file(tmp_path)
    hive = tmp_path / "labels" / "code=EMSR001" / "data.parquet"
    hive.parent.mkdir(parents=True)
    hive.write_bytes(src.read_bytes())
    frame, geoms = P.read_geometry_column(hive, ["code", "aoi", "acq_start", "acq_end"], "geometry")
    assert frame.code.tolist() == ["EMSR001", "EMSR001"]
    assert len(geoms) == 2


def test_country_aliases_unify_the_three_known_spellings():
    idx = _cems_index()
    idx["countries"] = [
        "Myanmar/Burma; Iran (Islamic Republic of)",
        "Bolivia (Plurinational State of)",
    ]
    out = P.harmonise_index("cems", idx)
    assert out.countries.tolist() == ["Myanmar; Iran", "Bolivia"]


def test_unlisted_country_names_are_kept_verbatim():
    out = P.harmonise_index("cems", _cems_index())
    assert out.countries.tolist() == ["Sweden", "Sweden"]


def test_implausible_dates_are_reported_not_dropped():
    idx = _cems_index()
    idx.loc[0, "acq_start"] = pd.Timestamp("1476-08-16")
    out = P.harmonise_index("cems", idx)
    assert len(out) == 2, "the row stays in the index"
    bad = P.implausible_dates(out)
    assert bad.code.tolist() == ["EMSR001"]
    assert list(bad.columns) == [
        "label_source",
        "code",
        "aoi",
        "acq_start",
        "acq_end",
        "acq_method",
        "sensor",
    ]


def test_simplify_keeps_only_polygonal_parts_of_a_collection():
    from shapely.geometry import GeometryCollection, LineString, MultiPolygon

    gc = GeometryCollection(
        [box(0, 0, 1, 1), LineString([(0, 0), (5, 5)]), MultiPolygon([box(2, 2, 3, 3)])]
    )
    out = P.simplify(gc, 1e-3)
    assert out.geom_type == "MultiPolygon"
    assert len(out.geoms) == 2
    assert out.area == 2.0


def test_index_geometry_is_none_where_a_label_set_has_no_extent():
    idx = _cems_index()
    idx.loc[1, ["minx", "miny", "maxx", "maxy"]] = np.nan
    geoms = P.index_geometry(P.harmonise_index("cems", idx))
    assert geoms[0].bounds == (0.0, 0.0, 1.0, 1.0)
    assert geoms[1] is None
