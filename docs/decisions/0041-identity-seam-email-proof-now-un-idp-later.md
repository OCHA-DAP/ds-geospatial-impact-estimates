---
status: "proposed"
date: 2026-11-27
deciders: Zack Arno
---

# Identity behind one seam: emailed proof now, UN identity provider later

## Context and Problem Statement

The provider side of the platform needs sign-in for mostly non-UN organisations. The UN
offers two routes (tenant guests, or the UN B2C tenant), both gated on an OICT architecture review with
no reply since 10 November and on an app registration we cannot create. The spike proved an
emailed single-use link with our own session. How do we build now without either committing
to home-grown auth as the final answer or waiting indefinitely?

## Decision Drivers

* Work must continue and be visible to colleagues while OICT is silent.
* The team's stance: auth is a solved problem; do not keep extending ad hoc auth.
* OICT may require a UN identity provider for an externally reachable site, or may make
  guests impractical for partners; either outcome must be absorbable.

## Considered Options

* Keep the spike's emailed link as the permanent sign-in.
* Build nothing provider-facing until the UN identity provider is granted.
* One `principal` seam: emailed proof behind it now, the Static Web App custom provider
  behind it later; records keyed on our own user id with provider identities as linked rows.

## Decision Outcome

Chosen option: the seam. Only identity verification changes when the provider changes;
membership, approvals and records are ours in every case and are built once.

### Consequences

* Good, because the preview keeps moving and the eventual swap touches one module.
* Good, because the target path can be tested now with the Static Web Apps CLI's auth emulator.
* Bad, because the interim link-and-cookie code (about two Functions) is written to be deleted.
* Bad, because two sign-in mechanisms exist in the codebase for a while.

## Pros and Cons of the Options

### Permanent emailed link
* Good, because it works today and proves control of an address, which is what open B2C
  sign-up proves too.
* Bad, because OICT or Cybersecurity may refuse it for an externally reachable site, and
  the team does not want to own password-less auth long term.

### Wait for the UN provider
* Good, because no throwaway code.
* Bad, because the gate has no date, and everything that does not depend on identity would
  wait with it.

## More Information

sign-in research of 2026-11-25 (options A and B, both need the Standard plan: ADR-0043).
Design: `docs/superpowers/specs/2026-11-27-provider-registry-design.md`. Revisit when the
review answer arrives.
