# chd-ds-token-issuer

A tiny, **shared, keyless** service that hands browsers short-lived read passes
(**SAS tokens**) so they can read map data (**PMTiles / Parquet**) directly from Azure
Blob Storage — with **no secret stored anywhere**.

- **Live endpoint:** `https://chd-ds-token-issuer.azurewebsites.net/api/token`
- **What it is:** an Azure **Function App** (Consumption plan, Python) in resource group
  `IMB-CHD-DataScience-EastUS2`. It runs only when called; at our traffic it's effectively free.
- **Portal:** [open in Azure Portal](https://portal.azure.com/#@unitednations.onmicrosoft.com/resource/subscriptions/3767353a-61dc-440a-b098-a362318edbe0/resourceGroups/IMB-CHD-DataScience-EastUS2/providers/Microsoft.Web/sites/chd-ds-token-issuer)

## Why this exists

Browsers read big map files straight from blob storage (fast, cloud-native). To do that
they need *some* credential. You never hand out the storage **account key** (it can do
everything, forever). Instead this service mints a **SAS**: read-only, scoped to one
folder, expires in 24h. It authenticates as the Function's **managed identity** (an Azure
"badge"), so there is no key or password stored in config. See ADR-0022.

## How to call it

```
GET /api/token?app=<app-id>&tier=<staging|prod>
```

- `app` (default `satellite-viewer`) and `tier` (default `prod`) pick **which folder** the
  token is scoped to. A bare `GET /api/token` returns the default (satellite-viewer / prod).
- Returns JSON. One request = **one** token, for the one scope you asked for.

```jsonc
{
  "account": "imb0chd0dev",
  "container": "projects",
  "base_url": "https://imb0chd0dev.blob.core.windows.net/projects/ds-geospatial-impact-estimates",
  "platinum_dir": "platinum-prod",     // the scoped folder (prod here; "platinum" for staging)
  "sas": "st=…&se=…&sp=rl&sr=d&sig=…", // the read pass itself; read-only, ~24h, this folder only
  "mode": "delegation-platinum",       // keyless (user-delegation). "scoped-platinum" would mean a fallback
  "expires": "2026-07-14T18:07:03Z"
}
```

Unknown `app`/`tier` → **HTTP 400** (that's the security gate — you can only get a token for
a folder someone deliberately registered below).

## How a frontend uses it

Fetch the token once on load, keep it in memory, use `sas` + `base_url` to read tiles.
Re-fetch before it expires.

```js
const t = await fetch(
  "https://chd-ds-token-issuer.azurewebsites.net/api/token?app=satellite-viewer&tier=prod"
).then(r => r.json());
// e.g. a PMTiles source:
const url = `${t.base_url}/${t.platinum_dir}/buildings/building_flags.pmtiles?${t.sas}`;
```

The browser talks to the issuer **only** to get the token; all the actual map bytes go
**directly** browser→blob. (The storage account also needs CORS to allow the app's origin.)

## Registered apps (the allow-list) — how to add one

The registered apps live in one place: the `ALLOWLIST` dict in [`function_app.py`](./function_app.py).
Each key is a valid `?app=` value; each maps to a storage account + folder.

To add an app:
1. Add an entry to `ALLOWLIST` (account, container, `project_prefix` = the folder, and the
   `dirs` its `?tier=` values map to).
2. If the new app's data is in a **different storage account**, that account needs the same
   role grant (see below) for our identity.
3. Redeploy: `./deploy.sh`.

Then `GET /api/token?app=<new-id>` works and is scoped to that app's folder.

## Permissions it depends on

The Function's **system-assigned managed identity**
(principal `ab58f738-0a28-4b2c-a69f-96800e6630d8`) must hold **`Storage Blob Data Reader`**
on each **storage account** it mints tokens for — at **account scope** (required for the
`getUserDelegationKey` call). Assigning a role needs **Owner / User Access Administrator**
(plain Contributor can't) — so this grant is an **IT / admin** step. Currently granted on
`imb0chd0dev`.

> Gotcha: "Reader" (management-plane) is **not** the same as "Storage Blob Data Reader"
> (data-plane). Only the latter works.

## Deploy / redeploy

`func` Core Tools are **not** assumed to be installed. `deploy.sh` handles the
Linux-Consumption-Python quirks (vendored deps + external run-from-package):

```bash
cd token-issuer
./deploy.sh            # builds vendored package, uploads to blob, points the app at it, restarts
```

Then verify:
```bash
curl -s https://chd-ds-token-issuer.azurewebsites.net/api/token | jq .platinum_dir
```

## Security model (why the SAS being public is fine)

The endpoint is **anonymous** — anyone can fetch a token. That's intentional: the SAS is
**read-only**, **scoped to the published tiles only**, and **expires in ~24h**. It grants
nothing a normal app visitor couldn't already read. It is **not** the account key; it can't
write, delete, or reach other folders. If a future app serves *sensitive* data, gate the
endpoint (API key / allowed-origins / Entra sign-in) before registering it.

## Resources

| Thing | Value |
|---|---|
| Function App | `chd-ds-token-issuer` (Consumption, Linux, Python 3.11) |
| Runtime storage | `chd0tokenissuer` (its own bookkeeping; no project data) |
| Resource group | `IMB-CHD-DataScience-EastUS2` (sub OCHA-PROD, `3767353a-…`) |
| Identity | system-assigned MI `ab58f738-0a28-4b2c-a69f-96800e6630d8` |
