# ADR-0004 — Plugin-neutral bounded experience learning

- Status: accepted by explicit owner implementation direction
- Date: 2026-08-10
- Owner: project owner
- Scope: behavior evidence, preference candidates, promotion and rollback

## Context

Engine experience must affect later decisions, but an unexplained domain change
is not an instruction and a learned preference cannot silently expand authority.
Domain-specific behavior remains in plugin-owned stores. A generic, versioned
promotion gate is needed before inferred behavior affects an active goal.

## Decision

1. Plugins declare namespaced `PreferenceSpecV1` values in their static manifest
   and may expose an optional cursor-based `ExperienceProvider`.
2. Heart validates batch identity and preference values, stores every signal
   exactly once, and advances the opaque provider cursor in the same transaction.
   Unknown preferences and capability families remain durable unlinked evidence.
3. A signal links only when plugin, target, entity, capability family,
   preference id and a GoalSpec effect selector all match.
4. `GoalSpecV2.preferences` is keyed by preference id. Plugin specialists read
   those values and translate them into their own domain semantics; core never
   interprets brightness, crates, temperature or equivalent meanings.
5. Explicit owner corrections may version a GoalSpec immediately, within the
   existing mandate and capability scope.
6. Unexplained control remains `INFERRED`. It never directly changes a GoalSpec,
   mandate, identity or authorization.
7. A candidate may enter shadow only after:
   - at least five equivalent examples;
   - examples on at least three distinct UTC dates;
   - at least 80% value and context consistency;
   - no explicit conflicting evidence;
8. Shadow is counterfactual, not evidence-consistency waiting. It lasts at least
   seven local calendar days, performs no dispatch, and records an opportunity
   only when the activation guard is true while the desired effect is observed
   false. Routine promotion requires at least three such real opportunities,
   at least 80% later externally observed agreement inside the declared template
   window, and no explicit conflict. A missing opportunity is not an agreement.
9. Preference-only candidates retain the same seven-day interval and must use
   independently observed outcomes where the preference can affect execution;
   evidence consistency alone cannot establish a physical effect.
10. Automatic promotion additionally requires `learning.low-risk` plus an active,
   exact `AutonomyProfileV1`; otherwise a proven routine becomes
   `ready_for_approval`. Sensitive preferences remain `explicit_only`.
11. Promotion records examples, old/new values, shadow outcome, the new GoalSpec
   version and an exact rollback patch. It invalidates the old goal plan cache.
12. Learning cannot add targets, entities, capability families, risk, privacy
    permission, mandate duration or execution authority.

## Alternatives considered

### Treat repeated behavior as implicit consent

Rejected. Observation is not authorization and repetition does not reveal intent.

### Put domain fields in Engine core

Rejected. A Homey brightness allowlist in Heart would make Homey the accidental
core schema and could not prove the same route in a warehouse or later plugin.

### Let a model decide when a habit is real

Rejected. Models may cluster or describe candidates, but scope, threshold,
promotion and rollback are deterministic and reproducible.

## Consequences

Learning is deliberately slow, inspectable and reversible. Plugins without an
experience provider keep working unchanged. Plugin feature extraction remains
domain-specific; cursor, evidence, candidate, shadow, GoalSpec versioning and
rollback remain Engine-wide.

## Safety and scientific impact

The fixed gate prevents post-hoc threshold movement. Promotion cannot widen
authority. Raw source identities and negative/conflicting outcomes are retained.
This is state/preference adaptation, not online weight training or observation
of a physical effect.

## Migration

Existing plugin rows retain their original grade and source. Import alone is not
enough: manifest, scope, threshold, mandate and shadow time must all pass. Legacy
budget-based preference fields remain readable but are not the generic route.

## Reversibility

Every promotion includes a rollback patch and new GoalSpec version. Disabling
automatic promotion leaves evidence and candidates intact and does not affect
explicit owner corrections.
