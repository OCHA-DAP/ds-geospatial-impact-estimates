---
status: "accepted"
date: 2026-07-15
deciders: zackarno (with IT for RBAC/resource sign-off)
---

# Parallel Static Web App host from the same branch, ahead of full migration

## Context and Problem Statement

ADR-0011 Phase 3 targets Static Web Apps + a token Function as the end-state host,
but when IT cleared SWA creation, several viewer routes still required the Python
App Service. How do we adopt the SWA without blocking on the remaining conversions,
without forking the frontend, and with a staging/review flow for changes?

## Considered Options

1. **Parallel SWA now: one codebase/branch, two deploy targets, build-time config
   switch; SWA borrows the App Service cross-origin for not-yet-converted routes** (this ADR).
2. Wait for full client-side conversion, then cut over to the SWA in one step.
3. Fork the frontend (separate SWA copy) and let the two drift.
4. SWA Standard tier with managed-function token endpoint from day one.

## Decision Outcome

Chosen: **Option 1.** The SWA (`chd-ds-satellite-impact-viewer`, **Free** tier) serves
the same `web/` build as the App Service, from the same `v1` branch:

* **Config switch** (`web/src/config.ts`): `VITE_TOKEN_URL` / `VITE_API_BASE` resolved
  at build time. **Unset ⇒ byte-identical classic build** (verified against a pristine
  build), so the App Service pipeline is untouched; the SWA build points tokens at the
  issuer (ADR-0022) and any legacy `/api` routes at the App Service origin.
* **Two workflows, one branch:** `azure-deploy.yml` (App Service; staging slot + gated
  prod, unchanged) and `swa-deploy.yml` (push → SWA production env; **PRs touching
  `web/` → SWA preview environments on the staging data tier + staging slot API**) —
  the code/staging split rides SWA preview environments and mirrors the existing
  `platinum` vs `platinum-prod` data split via the issuer's `tier` parameter.
* Deploys authenticate with the SWA **deployment token** (a GitHub secret), so CI and
  day-to-day publishing never depend on anyone's Azure RBAC/PIM state.
* Free tier suffices: no managed identity is needed *on the SWA* because token minting
  lives in the standalone Function (ADR-0022); custom domains (2) are included.

The migration then proceeded incrementally on the shared branch until nothing in the
client required the App Service (see ADR-0011's 2026-07-15 amendment) — reached the
same week, without a cutover event.

Option 2 rejected: serializes months of work behind an infra step and forfeits PR
preview URLs meanwhile. Option 3 rejected: drift — proven immediately in practice
(the SWA branch fell 12 commits behind `v1` and shipped unlabeled sources/broken
hover until rebased; that incident motivated merging to one branch). Option 4
rejected: pays Standard for a managed-function token the standalone issuer already
provides keylessly, and couples the token's lifecycle to one consumer app.

### Consequences

* Good — the SWA was live and reviewable from day one, with zero risk to the
  production App Service (its build and pipeline are provably unchanged).
* Good — every PR gets a live preview on staging data; merging to `v1` is the single
  gate for both hosts.
* Good — the SWA production env deploys ungated on push (acceptable while the App
  Service URL remains canonical). **Revisit before the SWA URL is advertised:** add
  branch protection / a gated environment, and decide the custom-domain question
  (deferred; needs one CNAME from the DNS owner + Contributor on the SWA).
* Bad — two CI workflows and two hostnames to keep in one's head during the interim.
* Bad — the App Service still runs (shared plan, ~$0 marginal) purely as the classic
  URL / stale-client fallback until a retirement decision is taken.

## More Information

* Resources: SWA `chd-ds-satellite-impact-viewer` (Free, RG IMB-CHD-DataScience-EastUS2,
  host `ashy-sea-03134990f.7.azurestaticapps.net`); token issuer per ADR-0022.
* Relates: ADR-0011 (v2 serving + phases; amended 2026-07-15), ADR-0022 (keyless SAS
  issuer), ADR-0021 (default-load latency — its "don't gate initial render" and
  "cache/static meta" options were implemented as part of this work).
