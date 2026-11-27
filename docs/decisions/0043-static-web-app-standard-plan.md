---
status: "proposed"
date: 2026-11-27
deciders: Zack Arno
---

# Move the Static Web App to the Standard plan

Supersedes the hosting-plan part of ADR-0023, which chose Free.

## Context and Problem Statement

ADR-0023 put the viewer on a Free Static Web App beside the App Service. The provider side
now needs two things Free does not offer: a custom sign-in provider (the UN tenant or the UN
B2C tenant; Free allows only Microsoft's preconfigured providers, which the UN tenant
refuses consent to) and a linked backend so the API on the App Service is served same-origin
under `/api`. Standard also raises custom domains from two to five.

## Decision Drivers

* Both UN sign-in options require Standard (Microsoft: custom authentication is Standard only).
* The target API runs on the App Service and must be same-origin.
* Cost: about USD 9 per month per app.

## Considered Options

* Stay on Free; serve the API cross-origin from the App Service with CORS and cross-site cookies.
* Standard.

## Decision Outcome

Chosen option: Standard, when the first of the two needs becomes actionable (the app
registration arrives, or the App Service is VNet-integrated). The change is one command with
the PIM Contributor role on the resource group; no IT request. Until then this ADR stays
`proposed`.

### Consequences

* Good, because UN sign-in and the linked backend become configuration, not architecture.
* Bad, because the viewer's hosting is no longer free; a small, recurring cost to record.

## Pros and Cons of the Options

### Stay on Free with a cross-origin API
* Good, because no cost.
* Bad, because cross-site cookies (`SameSite=None`) weaken the session model, every
  endpoint needs CORS, and UN sign-in is still impossible.

## More Information

sign-in research 2026-11-25; design `docs/superpowers/specs/2026-11-27-provider-registry-design.md`.
