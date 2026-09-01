"""Shared plumbing for the CEMS flood historical archive harvest.

The archive lands OUTSIDE this project's blob scope — container ``global``,
prefix ``copernicus_ems/flood/`` — because it is a general historical corpus,
not event-scoped project data. The code, however, deliberately reuses this
repo's machinery: ``gie.config`` credentials, the ``gie.blobio`` tuned
uploader, and the ``data_transfers.jsonl`` record shape.
"""

from __future__ import annotations

import dataclasses

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gie.config import Settings, load_settings

CONTAINER = "global"
BRONZE = "copernicus_ems/flood/bronze"
META = f"{BRONZE}/_meta"

ARCHIVE_API = "https://mapping.emergency.copernicus.eu/activations/api/activations/"
ARCHIVE_PAGE = "https://mapping.emergency.copernicus.eu/activations/{code}/"
NEW_PORTAL_MIN = 656  # first EMSR number served by the new-portal backend

PROVIDER = "Copernicus Emergency Management Service (rapid mapping)"
LICENCE = "CEMS free re-use with attribution (© European Union)"

# Downstream role of each product class for this corpus. REF (pre-event
# reference maps) is inventoried but not fetched; everything else is.
_TITLE_TO_CLASS = (
    ("reference", "REF"),
    ("grading", "GRA"),
    ("first estimate", "FEP"),
    ("delineation", "DEL"),
)


def classify_title(title: str | None) -> str:
    """Legacy product-card title -> product class (UNK = new family: harvest
    it anyway and let it show up in the ledger, exclusion is REF-only)."""
    low = (title or "").casefold()
    for needle, cls in _TITLE_TO_CLASS:
        if needle in low:
            return cls
    return "UNK"


def zip_blob_path(code: str, basename: str) -> str:
    return f"{BRONZE}/code={code}/{basename}"


def global_settings(stage: str) -> Settings:
    """This repo's Settings (credentials, account naming) pointed at the
    ``global`` container instead of the project container."""
    return dataclasses.replace(load_settings(stage), container=CONTAINER)


def coerce_ledger_dtypes(df):
    """Stabilize transfer-column dtypes. Columns that discovery never
    populates come out of parquet as all-NaN float64, and pandas >= 2 raises
    (rather than upcasts) when harvest later assigns strings into them."""
    for col in ("attempted_at", "uploaded_at", "sha256", "error"):
        if not str(df[col].dtype).startswith(("object", "str")):
            df[col] = df[col].astype(object).where(df[col].notna(), None)
    for col in ("http_status", "attempts", "size_bytes", "n_members"):
        df[col] = df[col].astype("Int64")
    return df


def make_session() -> requests.Session:
    """Session with a browser-ish UA (the CEMS backends 403 the default python
    UA) and retry/backoff on transient upstream errors."""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; OCHA-CHD CEMS flood archive)"
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s
