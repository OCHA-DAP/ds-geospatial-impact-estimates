"""Serving queries shared by the spike front ends.

Both viewers read the same gold damage-fact table (and CODAB geometry) through
DuckDB over blob, so the only difference between them is the rendering library.
Keeping the queries here means the Streamlit/pydeck and Solara/Lonboard apps
stay thin and provably consume identical data.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from gie import db
from gie.config import load_settings


def load_h3_damage(
    source: str = "microsoft", adm0: str = "VE", stage: str = "dev"
) -> pd.DataFrame:
    """Per-H3-cell damage metrics (wide), for the hexagon layer."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", f"source={source}", f"adm0={adm0}", "damage_facts.parquet")
    return con.execute(
        f"""
        SELECT unit_id AS h3,
            max(value) FILTER (WHERE metric='buildings_total')  AS buildings_total,
            max(value) FILTER (WHERE metric='buildings_damaged') AS buildings_damaged,
            max(value) FILTER (WHERE metric='damaged_fraction')  AS damaged_fraction,
            max(value) FILTER (WHERE metric='damage_pct_mean')   AS damage_pct_mean
        FROM read_parquet('{gold}') WHERE unit_type='h3' GROUP BY unit_id
        """
    ).df()


def load_adm2_damage(
    source: str = "microsoft", adm0: str = "VE", stage: str = "dev"
) -> gpd.GeoDataFrame:
    """All adm2 polygons for the country, left-joined to damage facts.

    Units without data keep null metrics (rendered as 'no data'), so the result
    is a proper choropleth with context around the affected municipality.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", f"source={source}", f"adm0={adm0}", "damage_facts.parquet")
    adm2 = settings.az_path("bronze", "source=codab", f"adm0={adm0}", "adm2.parquet")
    df = con.execute(
        f"""
        WITH facts AS (
            SELECT unit_id AS adm2_id,
                max(value) FILTER (WHERE metric='buildings_total')   AS buildings_total,
                max(value) FILTER (WHERE metric='buildings_damaged') AS buildings_damaged,
                max(value) FILTER (WHERE metric='damaged_fraction')  AS damaged_fraction
            FROM read_parquet('{gold}') WHERE unit_type='adm2' GROUP BY unit_id
        )
        SELECT a.adm2_id, a.adm2_name, ST_AsWKB(a.geometry) AS wkb,
               f.buildings_total, f.buildings_damaged, f.damaged_fraction
        FROM read_parquet('{adm2}') a
        LEFT JOIN facts f USING (adm2_id)
        """
    ).df()
    # DuckDB returns BLOBs as bytearray; shapely.from_wkb needs bytes.
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def damage_colors(
    fractions, *, na: tuple[int, int, int, int] = (200, 200, 200, 40)
) -> np.ndarray:
    """Map a damaged-fraction series (0..1, NaN allowed) to an RGBA uint8 array.

    Sequential yellow -> dark red; NaN renders as faint grey ('no data').
    """
    f = np.asarray(fractions, dtype="float64")
    out = np.empty((len(f), 4), dtype="uint8")
    valid = ~np.isnan(f)
    fc = np.clip(f[valid], 0.0, 1.0)
    out[valid, 0] = 240
    out[valid, 1] = (220 * (1 - fc)).astype("uint8")
    out[valid, 2] = (40 * (1 - fc)).astype("uint8")
    out[valid, 3] = 200
    out[~valid] = na
    return out
