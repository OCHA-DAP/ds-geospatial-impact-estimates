"""chd-ds-token-issuer — shared, keyless SAS token vendor.

Mints short-lived (24h), directory-scoped, READ-ONLY user-delegation SAS for
allow-listed apps, so browsers can read PMTiles/Parquet straight from blob without
any stored secret. Authenticates as this Function App's system-assigned managed
identity (via DefaultAzureCredential) — the identity must hold `Storage Blob Data
Reader` on each target storage account (account scope, for getUserDelegationKey).

Endpoint: GET /api/token?app=<id>&tier=<staging|prod>
  Defaults: app=satellite-viewer, tier=prod  → a bare GET returns the prod token,
  matching what the existing viewer client already fetches.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import (
    DataLakeServiceClient,
    DirectorySasPermissions,
    generate_directory_sas,
)

app = func.FunctionApp()

# Allow-list: which apps may get tokens, and for exactly which scope. A shared issuer
# NEVER mints for a caller-supplied arbitrary path — only these. Add an app = add an
# entry here (+ a Storage Blob Data Reader grant if it's a new storage account).
ALLOWLIST = {
    "satellite-viewer": {
        "account": "imb0chd0dev",
        "container": "projects",
        "project_prefix": "ds-geospatial-impact-estimates",
        "dirs": {"staging": "platinum", "prod": "platinum-prod"},
    },
}

_SAS_HOURS = 24
# Reuse one credential across warm invocations (token caching handled by the SDK).
_CRED = DefaultAzureCredential()


def _mint(cfg: dict, tier: str) -> dict:
    account = cfg["account"]
    container = cfg["container"]
    platinum_dir = cfg["dirs"][tier]
    directory = f"{cfg['project_prefix']}/{platinum_dir}"

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=_SAS_HOURS)
    svc = DataLakeServiceClient(
        f"https://{account}.dfs.core.windows.net", credential=_CRED
    )
    udk = svc.get_user_delegation_key(now, exp)
    sas = generate_directory_sas(
        account, container, directory,
        credential=udk,
        permission=DirectorySasPermissions(read=True, list=True),
        expiry=exp, start=now,
    )
    return {
        "account": account,
        "container": container,
        "base_url": f"https://{account}.blob.core.windows.net/{container}/{cfg['project_prefix']}",
        "platinum_dir": platinum_dir,
        "sas": sas,
        "mode": "delegation-platinum",
        "expires": parse_qs(sas).get("se", [None])[0],
    }


@app.route(route="token", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def token(req: func.HttpRequest) -> func.HttpResponse:
    app_id = req.params.get("app", "satellite-viewer")
    tier = req.params.get("tier", "prod")
    cfg = ALLOWLIST.get(app_id)
    if cfg is None or tier not in cfg["dirs"]:
        return func.HttpResponse(
            json.dumps({"error": "unknown app or tier", "app": app_id, "tier": tier}),
            status_code=400, mimetype="application/json",
        )
    try:
        body = _mint(cfg, tier)
    except Exception as e:  # noqa: BLE001 — surface a clean 503, log the detail
        logging.exception("user-delegation SAS mint failed")
        return func.HttpResponse(
            json.dumps({"error": "mint_failed", "detail": str(e)[:300]}),
            status_code=503, mimetype="application/json",
        )
    return func.HttpResponse(
        json.dumps(body),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )
