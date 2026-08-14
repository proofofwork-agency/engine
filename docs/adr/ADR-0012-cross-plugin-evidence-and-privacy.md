# ADR-0012 — Cross-plugin evidence and derived observation privacy

- Status: proposed; implementation of the evidence and privacy slice has
  landed as C2/C3. Owner signature still required.
- Owner: project owner
- Date: 2026-08-14

## Context

GOAL-0.2 M6 requires a Homey action to be justified by typed evidence from
`engine.context` without cross-plugin mutation and without turning evidence
into prompt glue. A global 128-observation cap silently dropped context
rows. Privacy was only checked against strategy self-declaration.

## Decision

1. Autonomy projections keep enrolled own-plugin entities and observations
   exact. Foreign context sources are capped at 16 entities and 32
   observations each, in deterministic order, with per-source truncation
   flags.
2. `STALE` foreign observations remain visible and lose evidence
   eligibility.
3. Optional `[[observation_privacy]]` manifest rules map property patterns
   to a privacy class. Undeclared properties inherit the provider query
   capability class, otherwise `sensitive` (fail closed).
4. `engine.context` declares `time.*` public, `sun.*` and `weather.*` local,
   `location.*` sensitive. A `local` grant cannot expose latitude.
5. Enrollments must include every strategy-declared privacy class.
6. `EvidenceRefV1` is the only way a proposal may cite evidence. Every id
   must resolve inside that evaluation's projection as `OBSERVED` or
   `DERIVED`, eligible, and sourced from the enrollment plugin or an
   enrolled context plugin. Unresolvable or stale evidence defers the
   binding in every mode.
7. Cross-plugin mutation remains forbidden.

## Alternatives

- Keep the global observation cap and hope context wins the slice.
- Let strategies self-declare privacy without source derivation.
- Allow uncited proposals for context-enrolled strategies.

## Consequences

Homey context-lighting can cite sun evidence. Live C5 still requires owner
presence. ADR-0008 bounds (one cognition hop, no wildcards, no cross-plugin
mutation) are unchanged.

## Safety / scientific impact

This is an authority and privacy boundary change. It does not certify
physical safety. Simulator 5/5 is not live evidence.

## Migration and reversibility

Existing enrollments without required grants cannot be recreated. Revert
the C2/C3 commits if the owner rejects this ADR.

## Reversibility

Yes, by revert. No live store rewrite is required.
