"""FastAPI serving layer for the damage-exposure viewer.

Thin HTTP layer over gie.serving (DuckDB-direct over blob). Serves the
common-model gold (gold/model=common): every source on one Overture building
base, coverage-aware. Responses are GeoJSON / JSON for the deck.gl + MapLibre
front end, cached in memory after first build.

Run: uv run --group api uvicorn api.main:app --reload --port 8077
"""

from __future__ import annotations

import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from gie.config import load_settings
from gie.serving import (
    export_workbook,
    list_sources,
    load_agreement,
    load_buildings,
    load_common_admin,
    load_common_h3,
    load_coverage_detail,
    load_native,
    load_source_extent,
)

app = FastAPI(title="Damage Exposure API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# API responses are deterministic + read-only until the data is refreshed, so let
# the browser keep its own copy — a reload or revisit is then instant instead of
# re-downloading the (multi-MB) layers. The server-side lru_cache covers repeats
# within a process; this covers the client across page loads. stale-while-
# revalidate keeps revisits instant while a fresh copy is fetched in the
# background. After a data refresh, restarting the app re-reads the new gold;
# clients pick it up within max-age (or on a hard refresh).
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"


def _json(content: str) -> Response:
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": _CACHE_CONTROL},
    )


@lru_cache(maxsize=1)
def _sources(adm0: str) -> list[str]:
    # event=None: the App Service serving layer is PINNED to the legacy un-evented
    # layout until its retirement (spec §4).
    return list_sources(adm0, event=None)


@lru_cache(maxsize=16)
def _common_h3_json(source: str, adm0: str) -> str:
    return load_common_h3(source, adm0, event=None).to_json(orient="records")


@lru_cache(maxsize=32)
def _common_admin_json(level: int, source: str, adm0: str) -> str:
    return load_common_admin(level, source, adm0).to_json()


@lru_cache(maxsize=8)
def _buildings_json(source: str, adm0: str) -> str:
    return load_buildings(source, adm0).to_json(orient="records")


@lru_cache(maxsize=8)
def _native_json(source: str, adm0: str) -> str:
    return load_native(source, adm0).to_json()


@lru_cache(maxsize=8)
def _extent_json(source: str, adm0: str) -> str:
    return load_source_extent(source, adm0, event=None).to_json()


@lru_cache(maxsize=2)
def _agreement_json(adm0: str) -> str:
    return load_agreement(adm0, event=None).to_json(orient="records")


# Metrics definition lives in gie.serving (shared with the platinum meta export).
from gie.serving import METRICS  # noqa: E402


@app.get("/api/sources")
def sources(adm0: str = "VE") -> dict:
    return {"sources": _sources(adm0), "adm0": adm0, "metrics": METRICS}


# --- /api/token: blob read for the v2 client, scoped to platinum/ (ADR-0011) ---
# The client reads PMTiles/values straight from blob, so the SAS is visible in the
# browser. That is fine BECAUSE it is scoped to this project's platinum/ directory
# only (read+list): it grants nothing but the published map tiles the app already
# shows everyone. We NEVER hand out the broad container SAS. Order of preference:
#   1. the shared keyless token issuer (chd-ds-token-issuer Function): a fresh 24h
#      user-delegation SAS per fetch, no secret stored anywhere;
#   2. a user-delegation SAS minted via the App Service managed identity
#      (when MI + Storage Blob Data Reader are in place) — keyless, auto-rotating;
#   3. else GIE_PLATINUM_SAS — a long-lived account-key SAS scoped to platinum/, set
#      as an app setting — the legacy fallback if the issuer is unreachable.
_SAS_HOURS = 24
_SAS_REFRESH_UNDER = timedelta(hours=6)
_token_cache: dict = {}

# The shared token issuer (see token-issuer/ on the swa-static-web-app branch). Its
# ?tier= maps to the same platinum dirs this app's GIE_TIER selects.
_ISSUER_URL = os.getenv(
    "GIE_TOKEN_ISSUER_URL", "https://chd-ds-token-issuer.azurewebsites.net/api/token"
)


def _issuer_token(s) -> tuple[str, datetime] | None:
    """Fetch a fresh keyless delegation SAS from the shared issuer; None on any failure."""
    import json

    tier = "prod" if s.tier == "prod" else "staging"
    try:
        url = f"{_ISSUER_URL}?app=satellite-viewer&tier={tier}"
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read())
        if d.get("mode") == "delegation-platinum" and d.get("sas"):
            exp = datetime.fromisoformat(d["expires"].replace("Z", "+00:00"))
            return d["sas"], exp
    except Exception as e:
        logging.warning("issuer token fetch failed (%s) — falling back", str(e)[:140])
    return None


def _se_expiry(sas: str) -> str | None:
    import urllib.parse

    return urllib.parse.parse_qs(sas).get("se", [None])[0]


def _mint_scoped_sas(s) -> tuple[str, datetime] | None:
    # Only attempt when a managed identity is actually present (App Service sets
    # IDENTITY_ENDPOINT), so there's no AAD/IMDS latency locally or on apps without MI.
    if not os.getenv("IDENTITY_ENDPOINT"):
        return None
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.filedatalake import (
            DataLakeServiceClient,
            DirectorySasPermissions,
            generate_directory_sas,
        )

        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=_SAS_HOURS)
        svc = DataLakeServiceClient(
            f"https://{s.account_name}.dfs.core.windows.net", credential=DefaultAzureCredential()
        )
        udk = svc.get_user_delegation_key(now, exp)
        sas = generate_directory_sas(
            s.account_name,
            s.container,
            f"{s.project_prefix}/{s.platinum_prefix}",
            credential=udk,
            permission=DirectorySasPermissions(read=True, list=True),
            expiry=exp,
            start=now,
        )
        # Generating a SAS never checks RBAC; only a read does. Verify before handing
        # it out so a missing Data Reader role falls back instead of serving a dud.
        probe = f"https://{s.account_host}/{s.container}/{s.project_prefix}/{s.platinum_prefix}/values/facts-admin.parquet?{sas}"
        urllib.request.urlopen(urllib.request.Request(probe, headers={"Range": "bytes=0-1"}), timeout=10)
        return sas, exp
    except Exception as e:
        logging.warning("MI scoped-SAS mint failed (%s) — using GIE_PLATINUM_SAS", str(e)[:140])
        return None


@app.get("/api/token")
def token() -> dict:
    """Blob read for the v2 client (PMTiles + hyparquet), scoped to platinum/ — never
    the broad container SAS (ADR-0011)."""
    s = load_settings()
    now = datetime.now(timezone.utc)
    c = _token_cache.get("v")
    if not c or c["exp"] - now < _SAS_REFRESH_UNDER:
        issued = _issuer_token(s)
        minted = None if issued else _mint_scoped_sas(s)
        if issued:
            sas, exp = issued
            c = {"sas": sas, "exp": exp, "mode": "delegation-platinum", "expires": exp.isoformat()}
        elif minted:
            sas, exp = minted
            c = {"sas": sas, "exp": exp, "mode": "delegation-platinum", "expires": exp.isoformat()}
        elif os.getenv("GIE_PLATINUM_SAS"):
            sas = os.getenv("GIE_PLATINUM_SAS").lstrip("?")
            # static scoped SAS; re-check hourly so MI can take over once it's wired up
            c = {"sas": sas, "exp": now + timedelta(hours=1), "mode": "scoped-platinum",
                 "expires": _se_expiry(sas)}
        else:
            # no scoped SAS available — leave converted layers unserved rather than
            # ever exposing the broad container SAS
            c = {"sas": "", "exp": now + timedelta(minutes=5), "mode": "unavailable", "expires": None}
        _token_cache["v"] = c
    return {
        "account": s.account_name,
        "container": s.container,
        "base_url": f"https://{s.account_host}/{s.container}/{s.project_prefix}",
        # The tier's platinum dir ("platinum" on dev/staging, "platinum-prod" on
        # the prod slot) — the client builds all PMTiles/values URLs under this.
        "platinum_dir": s.platinum_prefix,
        "sas": c["sas"],
        "mode": c["mode"],
        "expires": c["expires"],
    }


@app.get("/api/common/h3")
def common_h3(source: str, adm0: str = "VE") -> Response:
    return _json(_common_h3_json(source, adm0))


@app.get("/api/common/admin/{level}")
def common_admin(level: int, source: str, adm0: str = "VE") -> Response:
    return _json(_common_admin_json(level, source, adm0))


@app.get("/api/buildings")
def buildings(source: str, adm0: str = "VE") -> Response:
    return _json(_buildings_json(source, adm0))


@app.get("/api/native")
def native(source: str, adm0: str = "VE") -> Response:
    return _json(_native_json(source, adm0))


@app.get("/api/extent")
def extent(source: str, adm0: str = "VE") -> Response:
    return _json(_extent_json(source, adm0))


@app.get("/api/agreement")
def agreement(adm0: str = "VE") -> Response:
    return _json(_agreement_json(adm0))


@lru_cache(maxsize=2)
def _coverage_detail_json(adm0: str) -> str:
    return load_coverage_detail(adm0, event=None).to_json()


@app.get("/api/coverage_detail")
def coverage_detail(adm0: str = "VE") -> Response:
    return _json(_coverage_detail_json(adm0))


@lru_cache(maxsize=1)
def _export_xlsx(adm0: str) -> bytes:
    return export_workbook(adm0)


@app.get("/api/export.xlsx")
def export_xlsx(adm0: str = "VE") -> Response:
    """Per-admin-unit, per-source damage table — one sheet per admin level."""
    return Response(
        _export_xlsx(adm0),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; "
            "filename=ven_earthquake_damage_compilation_by_admin.xlsx"
        },
    )


# Serve the built SPA (web/dist) at the root, mounted AFTER all /api routes so it
# only catches everything else. In local dev the dist may not exist (Vite serves
# it on :5173), so mount only when present.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
