# Damage Analysis Platform: provider registry and submission back end

**Date:** 2026-11-27
**Status:** draft for review (not approved; nothing built from it yet)
**Driver:** the form spike (branch `spike/form-auth`, PR #174) proved the provider experience:
organisation sign-up, members, emailed sign-in, the three-level submission form, records on
blob. It was built as a throwaway. This document is the design for promoting it into the
platform's provider side, structured so the pieces that depend on IT (identity provider,
database reachability, hosting plan) can be swapped in as they are granted, and so one
developer can exercise the whole system alone.

Companion decisions: [ADR-0041](../../decisions/0041-identity-seam-email-proof-now-un-idp-later.md)
(identity seam), [ADR-0042](../../decisions/0042-registry-store-and-api-runtime.md) (registry
store and API runtime), [ADR-0043](../../decisions/0043-static-web-app-standard-plan.md)
(Standard plan, supersedes ADR-0023's Free choice).

## Decisions needed before building

Each has a recommendation; the choice is the team's.

1. **What ships first while OICT is silent.** (a) Keep the preview moving: put the registry
   behind a repository interface, implement it on blob JSON now, ship membership, approvals
   and delivery states to the PR preview so colleagues keep grading. (b) Freeze the preview on
   the spike and build the Python API against Postgres through the laptop tunnel, deploying
   nothing until VNet integration lands. Recommendation: (a). The interface is needed either
   way, and (b) produces nothing visible for an unknown number of weeks.
2. **Interim API language.** Follows from 1. Under (a) the Node Functions stay as the interim
   API and are ported to Python when the VNet-integrated App Service exists. Under (b) Python
   from day one. Recommendation: (a), accepting a port of about 500 lines later.
3. **Approval model.** The spike is self-service: register and you are in. Under the sign-in
   option the research recommends (UN B2C, open sign-up), our registration approval
   is the only access control. Proposal: an organisation is `pending` until a staff member
   approves it; members join by invitation from an existing member or by a join request a
   member accepts; the first member is the organisation's admin. Needs confirming.
4. **Sign-in option A or B.** UN tenant with guests, or the UN's B2C tenant with self-service
   sign-up. The research behind this is in the shared artifact linked at the end; its
   recommendation is B. This design does not depend on the choice; both arrive through the
   same Static Web App custom provider and the same principal seam.
5. **When the interim reaches the production host.** Today any push to `v1` touching
   `web/**` or `api-spike/**` deploys to the public viewer host. Merging the provider side
   there with dev credentials baked into the bundle is not acceptable. Two routes: (a) stay
   on a long-lived branch with the PR preview until the config seam reads Static Web App
   application settings, which a Contributor can set and the PIM-eligible role covers, so no
   IT request; (b) never merge the interim and wait for the target. Recommendation: (a),
   with `STORE=prod` meaning a `registry-prod/` prefix with its own scoped credential,
   mirroring the viewer's staging and prod data split; until then `STORE=prod` raises.

## Constraints (facts, checked 2026-11-25 to 27)

- **Postgres is private-endpoint only** since 2026-09-30. Reachable from Databricks, from a
  laptop through the Databricks SSH tunnel, and from App Services that OICT has
  VNet-integrated. Not reachable from Static Web App managed Functions (no VNet path) nor
  from our App Service fallback `chd-ds-geospatial-impact-viewer` (not integrated). Some team
  App Services are integrated, so it is a request with precedent, not a new capability.
- **The Static Web App is on the Free plan.** Free allows only Microsoft's preconfigured
  sign-in providers and no linked backend. A custom provider (UN tenant or UN B2C) and a
  linked App Service both need Standard. Custom domains: two on Free, five on Standard.
- **UN sign-in is gated on an architecture review that has not answered yet**, after which
  OICT can create an app registration. The UN tenant refuses consent to Microsoft's shared
  Static Web Apps registration (seen 25 Nov: "Need admin approval"), so the built-in
  provider is unusable for UN accounts.
- **No file uploads, ever.** Providers submit links; the platform fetches and validates.
  Fetching provider-controlled bytes is isolated (size cap, type check, timeout).
- **A sign-in action emails exactly one address**, the one typed. Asserted by a test.
- **Emailed links need a hostname the team controls.** Links built from a generic cloud
  hostname were flagged by Safe Browsing. Hostname under datascience.unocha.org (DNS record
  from OCHA's technical support, zone `imb-dns`, read-only to us).
- **Mail run modes follow the team convention** (KB `infrastructure/email-testing.md`):
  unset means safe; only explicit production config sends real mail.

## Target architecture and the interim

| Part | Interim (buildable now) | Target (after IT grants) | What changes |
|---|---|---|---|
| Front end | Static Web App, Free, generated hostname | Same app, Standard, `<name>.datascience.unocha.org` | Plan and DNS only |
| API | Node managed Functions in `api-spike/` | Python (FastAPI, ocha-stratus) on the App Service in the shared plan, VNet-integrated, linked as the SWA backend so `/api` stays same-origin | Port of the handlers; URL paths unchanged |
| Identity proof | Emailed single-use link, our session cookie | UN identity provider through the SWA custom provider; SWA session | The code behind one function (ADR-0041) |
| Registry | Blob JSON repository with ETag concurrency, dev account | Postgres, team server, by private IP | Repository implementation (ADR-0042) |
| Delivery files | Fetched into bronze on blob | Same | Nothing |
| Mail | Listmonk transactional endpoint, one recipient | Same | Nothing |
| Configuration | `secrets.json` written by the deploy workflow (dev credentials only) | App settings or Key Vault references | One config module |

Standalone Function apps were considered and rejected: the Consumption plan has no VNet path,
and the plans that do cost money and are their own resource request.

## Seams

Every seam is one module with one interface. Nothing outside the module knows which
implementation is behind it.

| Seam | Interface | Interim | Target |
|---|---|---|---|
| `principal` | `principal(request) -> {user_id, email, verified_by, verified_at} \| null` | Reads our session cookie, looks up the session row | Reads the client principal header the Static Web App adds after UN sign-in |
| `registry` | Repository: organisations, members, join requests, products, deliveries, sessions, link tokens, audit | Blob JSON, one object per record plus small indexes, `If-Match` on every write | Postgres tables, transactions |
| `mail` | `send(to, subject, html)`, exactly one `to` | Listmonk `/tx` | Same |
| `config` | `secret(name)`, fails loudly when missing | `secrets.json` from the workflow | App settings / Key Vault |
| `fetcher` | `fetch_validated(url, limits) -> file + facts` | Same code, run inside the Function | Isolated worker |

Rules that make the seams real:

- Records key on our own user id. An identity (email proof, later a UN object id) is a
  linked row under that user. Changing identity provider adds a row, never migrates records.
- Authorization (membership, roles, organisation state) lives in the registry. UN groups and
  app roles are never consulted.
- "Identity verified" is one event in the state machine, whatever produced it.
- The parts that die when the provider changes are in one folder: link issue and redeem,
  cookie minting, the one mail that carries a link.

## Domain model and states

Entities: `user`, `identity` (per user, per provider), `organisation`, `membership`
(user, organisation, role `admin`/`member`), `join_request`, `product` (a provider's product
definition: columns, geometry mode, damage mapping, extent mode), `delivery` (one product
version for one event: links, dates, headline numbers), `session`, `link_token` (single use),
`audit` (who did what, when), `outbox` (mail captured in test modes).

States:

- organisation: `pending` → `approved` → `suspended`. Only `approved` organisations submit.
- membership: `invited` → `active` → `removed`. Removal ends the member's sessions.
- join request: `open` → `accepted` | `declined`.
- delivery: `submitted` → `validated` | `rejected` → `published`. Validation fetches the two
  links (product, analysed extent) and records the facts it read. A late extent is an edit of
  the delivery, not a new one.

One address belongs to one organisation. An organisation has at least one admin.

## Run modes and the one-developer sandbox

- `MAIL_MODE`: `capture` (default; mail goes to the outbox table, nothing sent), `redirect`
  (every message to `MAIL_REDIRECT_TO` with the intended recipient in the subject, subject
  prefixed `[TEST]`), `real`. Unset or malformed is `capture`; a bad value raises.
- `STORE`: `local` (Azurite blob emulator, later a local Postgres), `dev`, `prod`. Unset is
  `local`. The PR preview runs `STORE=dev` with `MAIL_MODE=real` (colleagues must receive
  their links; subjects carry `[TEST]` while the store is not `prod`); production sets `prod`
  and `real` explicitly in the workflow. The outbox page is served only when `STORE=local`,
  so a single-use link is never readable from a deployed URL.
- `scripts/reset` drops the store for the selected tier (never `prod`) and loads fixtures:
  three organisations in each state, members in each role, deliveries in each state.
- A dev-only page lists the outbox so emailed links can be clicked without email.
- Identities: plus addressing (`name+orgA@un.org`) gives distinct addresses in one inbox.
  To verify with one send before relying on it.
- Being several people: browser profiles for manual play; the puppeteer scripts drive
  multi-actor flows (a partner registers, a staff member approves, a colleague joins).
- The UN sign-in path without OICT: the Static Web Apps CLI (`swa start`) emulates the
  built-in auth with a local login page where a name, provider and roles are typed. The
  target `principal` implementation is tested against it on the laptop.

## Carried forward from the security review (2026-11-20)

Sessions become rows and are revocable on logout and removal (O3). Emailed links are single
use and redeemed by a POST from a landing page so mail scanners do not burn them (O4).
Listings are scoped to the caller's organisation; staff see all (O5). Throttles live in the
registry, per address and per source address (O7). Clients get generic error text; detail
goes to logs (O8). Logout is a POST. Secrets are dev-tier only until the config seam moves
to app settings (O1, O2).

## IT dependencies and what each unlocks

| Request | To whom | Unlocks |
|---|---|---|
| DNS record `<name>.datascience.unocha.org` → the app | OCHA technical support | Clean hostname; stable redirect URI for the app registration |
| Static Web App to Standard | Ourselves, via PIM Contributor (about USD 9/month) | Custom sign-in provider; linked backend; five domains. ADR-0043 |
| VNet integration of the App Service | OICT | Python API reaching Postgres; the registry target |
| Architecture review answer | OICT review board (pending) | Any app registration |
| App registration (option A or B) | OICT via Unite | UN sign-in through the custom provider |

Nothing in the interim column waits on any of these.

## From the spike: keep, port, delete

Keep: the pages in `web/public/form-spike/` (renamed out of "spike"), the form logic and
validation, the single-recipient test, the puppeteer flows, the Listmonk relay pattern.
Port: the Function handlers into the seams above (interim: same Node; target: Python).
Replace: the blob layout (`_organisations/`, `_contacts/`) with the repository's layout;
self-service registration with the approval model. Delete when the target lands: link issue
and redeem, the cookie code, `secrets.json`.

## Calls made after the builder check

A reviewer read the draft as the person who would build it. These are my answers; each is a
default that can be overturned in review.

- **Staff.** Staff are members of one internal organisation flagged `is_staff` (OCHA CHD
  Data Science). It is created by the fixtures and by a one-off bootstrap in production that
  reads `STAFF_EMAILS` from configuration on first sign-in; after that, staff add staff like
  any admin adds members. Approve and reject are web actions by a signed-in staff member, not
  scripts. The `principal` carries no role; roles come from membership lookups in the
  registry. In the target, staff identity can additionally be asserted by the UN account
  domain, but the registry membership stays the authority.
- **Admin versus member.** Admins invite, remove, accept join requests and edit the
  organisation; members submit and edit their own deliveries. The last admin cannot be removed.
- **Validation in the interim is HTTP-level.** On submit, the Function fetches each link
  with a size cap and timeout and records status, content type, size, checksum and the facts
  the browser-side reader reported. Parsing provider files on the server is the target's
  isolated worker, not the interim. Keeps the port small and O9 out of the interim.
- **Validation runs synchronously on submit.** No queue in the interim. `published` is set by
  a staff action once the product is in the viewer; wiring the registry to the harmonise and
  promote pipeline is future work, noted under out of scope. A late extent edit returns the
  delivery to `submitted` and revalidates.
- **Products are versioned.** A delivery pins a product version. Editing a product definition
  creates a new version; earlier deliveries keep theirs. The form stays one page, pre-filled
  from the latest version.

## Out of scope

Choosing the platform name. The viewer itself (stays public). Raster validation beyond
recording the links. Staff review tooling beyond approve and reject. Retiring the App
Service fallback (it becomes the API host instead).

## Left to the builder

Blob object layout and index shape for the interim repository; the exact validation facts
recorded per delivery; fixture content; the dev outbox page's look; test structure.

## Where the sign-in research lives

The comparison of the spike with the UN sign-in options, with diagrams, is the artifact
"Spike versus Entra" (https://claude.ai/artifact/MmdWkEAgDv8XppNC4FqCwd, shared with the OCHA
Centre organisation on claude.ai). The catalogue research it rests on is kept out of this
public repository on purpose; it lives beside the artifact source in the maintainer's clone
(`docs/provider-sign-in/`, excluded from git) and can be shared on request.
