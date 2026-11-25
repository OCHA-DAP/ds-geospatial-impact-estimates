"""Helpers for the shared, country-keyed CODAB reference tree (spec §3).

CODAB lives OUTSIDE the event trees (``bronze/source=codab/adm0=<XX>/``,
``event=None``) and is reused across events. Countries differ in real admin
depth (VE: adm3; CO: adm2 — FieldMaps pads a fake adm3 that ingest_codab
skips), so consumers ask for the deepest level actually ingested instead of
assuming one.
"""

from __future__ import annotations

import ocha_stratus as stratus


def deepest_level(settings, adm0: str, *, stage: str = "dev") -> int:
    """Deepest CODAB admin level ingested for a country — fail loudly on none."""
    container = stratus.get_container_client(stage=stage, container_name=settings.container)
    for lvl in (3, 2, 1):
        p = settings.blob_path(
            "bronze", "source=codab", f"adm0={adm0}", f"adm{lvl}.parquet", event=None
        )
        if container.get_blob_client(p).exists():
            return lvl
    raise RuntimeError(f"no CODAB adm1+ parquet for {adm0} — run ingest_codab first")
