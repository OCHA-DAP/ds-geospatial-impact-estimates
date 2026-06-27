---
status: "accepted"
date: 2026-06-27
deciders: zackarno
---

# How the deployed web app authenticates to Azure Blob

## Context and Problem Statement

The viewer is deployed as an Azure App Service Linux web app
(`<app-name>`, on `<app-service-plan>`, with a `staging`
slot). At runtime the FastAPI/DuckDB serving layer reads the gold/silver
GeoParquet from blob (`<dev-blob-account>`). How should the *deployed* app present
credentials to blob, given the deployer's current RBAC (Website Contributor on
the resource group + Storage Account Contributor on `<dev-blob-account>`, but **no**
`Microsoft.Authorization/roleAssignments/write`)?

## Decision Drivers

* Must work within the deployer's current permissions (ship staging now).
* Minimise stored secrets and rotation burden, especially before a wider
  audience.
* Keep the serving code (DuckDB azure extension) simple.

## Considered Options

* SAS token as an app setting (read into `DSCI_AZ_BLOB_DEV_SAS`)
* System-assigned managed identity + Storage Blob Data Reader on the account
* Key Vault reference for the SAS in app settings

## Decision Outcome

Chosen for now: **SAS token as a (sticky) app setting**, per slot. It is the
only option that works end-to-end within the current RBAC, matches how the
sibling `chd-ds-*` apps inject secrets, and needs no new infrastructure. The SAS
is set as a **slot setting** (sticky) so prod and staging keep their own and it
does not move on swap. The raw token is never handled by the agent — it is set
from the operator's shell env (`! az webapp config appsettings set ...`).

**Planned upgrade (before wider rollout): managed identity.** Give the web app a
system-assigned identity and grant it **Storage Blob Data Reader** on
`<dev-blob-account>`, then switch `db.py` from a `CONNECTION_STRING` SAS secret to the
DuckDB azure extension's **credential chain** provider (which uses the identity
on Azure). This removes the stored secret entirely.

### Consequences

* Good, because staging ships immediately with no extra infra or elevated perms.
* Good, because sticky slot settings keep the auth correct across swaps.
* Bad, because a long-lived SAS lives in app settings (inspectable, expires, must
  be rotated) — acceptable for dev-blob, non-sensitive data, but not ideal for a
  public, wider-audience app.
* Neutral, because the upgrade is well-bounded: a one-time role grant by a
  storage owner + a small `db.py` change; no data-model impact.

## Pros and Cons of the Options

### SAS token as an app setting (chosen now)

* Good, because it works within Website Contributor + Storage Account
  Contributor, no role-assignment write.
* Good, because the serving code already builds a DuckDB secret from the SAS.
* Bad, because it is a stored, expiring secret that needs rotation.

### Managed identity + Storage Blob Data Reader (planned upgrade)

* Good, because no stored secret, no rotation, identity-scoped and auditable.
* Bad, because the role grant needs `roleAssignments/write` on the storage
  account, which the current identity lacks → a one-time owner action.
* Neutral, because it needs a small `db.py` change to use the credential chain.

### Key Vault reference

* Good, because the secret is centralised and access-controlled.
* Bad, because it adds a Key Vault + access policy + the app's identity granted
  get-secret — more infrastructure than managed identity for the same goal, and
  still ultimately a SAS to rotate.

## More Information

Revisit when moving the app to a wider audience or to prod data: do the managed
identity upgrade then (it also pairs naturally with reading `<prod-blob-account>`,
where the deployer already holds Storage Blob Data Reader).

## Deployment notes (staging runbook)

Target: resource group `<resource-group>`, plan `<app-service-plan>`
(P0v3 Linux), app `<app-name>` + a `staging` slot. Identity
needs Website Contributor on the RG (create/deploy) and Storage Account
Contributor on `<dev-blob-account>` (data). No CI — code zip-deploy with Oryx build,
matching the sibling `chd-ds-*` apps.

**App shape.** One Linux Python app serves both the API and the SPA: FastAPI
mounts the Vite build (`web/dist`) at `/` after the `/api` routes (`api/main.py`);
`asgi.py` is the gunicorn entry point (adds `src/` to the path, exposes `app`).
`requirements.txt` is generated from the lock: `uv export --no-dev --group api
--no-emit-project --no-hashes` (main + api only; no etl/ocha-lens). `web/dist`
stays gitignored and is built per deploy.

**Create + configure (CLI).**
- `az webapp create -g <rg> -p <app-service-plan> -n <app> --runtime "PYTHON:3.13"`
- `az webapp deployment slot create -g <rg> -n <app> --slot staging`
- per slot: `az webapp config set --startup-file "gunicorn asgi:app -k
  uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000" --always-on true`
- per slot: `--settings SCM_DO_BUILD_DURING_DEPLOYMENT=true` and
  `--slot-settings STAGE=dev` (+ the SAS as a sticky slot setting, set from the
  operator's shell env — never on the agent's command line).

**Build + deploy.** `cd web && npm run build`; then zip exactly
`api src web/dist requirements.txt asgi.py` and
`az webapp deploy --slot staging --src-path deploy.zip --type zip`. Oryx runs
`pip install -r requirements.txt` on the server, then the startup command.

**Gotcha that cost the most time — azure-extension TLS.** The DuckDB `azure`
extension's *default* transport could not verify TLS to blob on the App Service
image: `IOException ... Problem with the SSL CA cert (path? access rights?)`.
Important: the SAS was fine, and the system bundle (`/etc/ssl/certs/
ca-certificates.crt`) existed and was readable — the extension just wasn't using
it, and it does **not** honour `CURL_CA_BUNDLE` (DuckDB's extension *downloads*
over HTTPS worked, proving it's specific to the azure transport). Per the azure
extension docs the fix is, in `db.py`:
`SET azure_transport_option_type = 'curl';` **and** point **`CURL_CA_INFO`** (a
PEM file — not `CURL_CA_BUNDLE`) at `certifi.where()`. With both, blob reads
succeed. No-op locally where the default store already works.

**Verification.** `/` → 200 (SPA), `/api/sources` → 200, `/api/common/admin/3`
→ 200 (first call ~15 s cold — DuckDB + 4 MB GeoJSON build — then lru-cached);
headless browser render-check passes with no console errors. Promote with a slot
swap once verified.
