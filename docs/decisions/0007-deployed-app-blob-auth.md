---
status: "accepted"
date: 2026-06-27
deciders: zackarno
---

# How the deployed web app authenticates to Azure Blob

## Context and Problem Statement

The viewer is deployed as an Azure App Service Linux web app
(`chd-ds-geospatial-impact-viewer`, on `DsciAppServicePlan`, with a `staging`
slot). At runtime the FastAPI/DuckDB serving layer reads the gold/silver
GeoParquet from blob (`imb0chd0dev`). How should the *deployed* app present
credentials to blob, given the deployer's current RBAC (Website Contributor on
the resource group + Storage Account Contributor on `imb0chd0dev`, but **no**
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
`imb0chd0dev`, then switch `db.py` from a `CONNECTION_STRING` SAS secret to the
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
identity upgrade then (it also pairs naturally with reading `imb0chd0prod`,
where the deployer already holds Storage Blob Data Reader). Deployment specifics
live in the app's App Service config (startup `gunicorn asgi:app -k
uvicorn.workers.UvicornWorker`, `SCM_DO_BUILD_DURING_DEPLOYMENT=true`).
