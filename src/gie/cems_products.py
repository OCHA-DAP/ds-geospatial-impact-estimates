"""Authoritative CEMS product selection, keyed on the manifest's own metadata.

Copernicus EMS re-issues products (``version_number``) and adds monitoring
updates (``monitoring_number``); ``lens.cems.get_products`` (cached to bronze)
carries both, plus ``status_code`` and ``delivery_time``. To avoid counting
superseded data, we keep — per ``product_id`` — only the latest
``version_number`` among *delivered* products (``status_code == 'F'``, the only
ones with a ``download_url``). The single most recent product per AOI (highest
``monitoring_number``, then ``version_number``) is flagged ``is_latest``: the one
to attribute building-level impact from. Superseded products still appear nowhere
downstream. Display labels are derived from ``monitoring_number`` /
``version_number`` — no invented metadata; the raw fields travel alongside.

Both ``cems_coverage`` and ``harmonize_cems`` drive off this, so coverage and
damage always agree on which products are live.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

# CEMS product status: finished / delivered (the only status with a download_url).
_DELIVERED = "F"


def read_layer(zip_bytes: bytes, suffix: str) -> gpd.GeoDataFrame | None:
    """First shapefile whose name contains ``suffix``, reprojected to EPSG:4326.

    CEMS GRA zips bundle several layers (``areaOfInterestA``, ``imageFootprintA``,
    ``notAnalysedA``, ``builtUpA`` damage areas, ``builtUpP`` damage points, …);
    callers pick the one they need. Returns None if absent.
    """
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(io.BytesIO(zip_bytes)).extractall(d)
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".shp") and suffix in f:
                    return gpd.read_file(os.path.join(root, f)).to_crs(4326)
    return None


def _label(monitoring_number: int, version_number: int) -> str:
    """Human label derived from the real fields (not stored CEMS text)."""
    base = "Initial" if monitoring_number == 0 else f"Monitoring {monitoring_number}"
    return f"{base} (v{version_number})"


def active_products(
    settings, activation: str, *, event: str | None, stage: str = "dev"
) -> pd.DataFrame:
    """Delivered CEMS products with superseded versions dropped.

    One row per ``product_id`` at its max ``version_number``. Columns are the
    manifest's own fields (``product_id``, ``aoi_number``, ``aoi_name``,
    ``product_type``, ``monitoring_number``, ``version_number``,
    ``delivery_time``) plus ``zip_name`` (the ``download_url`` basename, which
    equals the bronze zip filename), a derived ``label``, and ``is_latest`` (the
    most recent product per AOI). Empty frame if no manifest is present yet.
    """
    prefix = settings.blob_path("bronze", "source=copernicus_ems", f"code={activation}", event=event)
    mans = sorted(
        b
        for b in stratus.list_container_blobs(
            name_starts_with=prefix, stage=stage, container_name=settings.container
        )
        if "products_" in b and b.endswith(".parquet")
    )
    if not mans:
        return pd.DataFrame()
    raw = stratus.load_blob_data(mans[-1], stage=stage, container_name=settings.container)
    man = pd.read_parquet(io.BytesIO(raw))

    df = man[(man["status_code"] == _DELIVERED) & man["download_url"].notna()].copy()
    df["zip_name"] = df["download_url"].str.rsplit("/", n=1).str[-1]
    df["monitoring_number"] = df["monitoring_number"].fillna(0).astype(int)
    df["version_number"] = df["version_number"].astype(int)

    # Supersession: keep the latest version per product_id (delivery_time breaks ties).
    df = (
        df.sort_values(["product_id", "version_number", "delivery_time"])
        .drop_duplicates("product_id", keep="last")
        .reset_index(drop=True)
    )
    df["label"] = [
        _label(m, v)
        for m, v in zip(df["monitoring_number"], df["version_number"], strict=True)
    ]
    # Latest product per AOI = the one to attribute building-level impact from.
    latest_idx = (
        df.sort_values(["monitoring_number", "version_number", "delivery_time"])
        .groupby("aoi_number")
        .tail(1)
        .index
    )
    df["is_latest"] = df.index.isin(latest_idx)
    return df[
        [
            "product_id",
            "aoi_number",
            "aoi_name",
            "product_type",
            "monitoring_number",
            "version_number",
            "delivery_time",
            "zip_name",
            "label",
            "is_latest",
        ]
    ]
