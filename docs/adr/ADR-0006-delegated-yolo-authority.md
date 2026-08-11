# ADR-0006 — Owner-delegated low-risk routine authority

- Status: superseded by ADR-0008
- Date: 2026-08-10
- Owner: project owner
- Scope: persistent YOLO profile, derived mandates, revocation and Homey tranche

This ADR records the earlier target-specific tranche. New authority is no longer
created through this route: `yolo` is a global mode alias, and generic authority
requires an exact `AutonomyEnrollmentV2`. Existing profile rows remain typed
legacy audit and compatibility data.

## Context

Repeated external behavior is not consent. Normal routine learning therefore
ends at local approval. The owner nevertheless wants an explicitly enrolled
mode in which Engine may promote a proven low-risk routine without approving
each routine instance. That delegation must not let a model, template compiler
or learner enlarge target, device, capability, privacy, risk or parameter scope.

## Decision

1. `engine yolo enable` creates a persistent, owner-activated
   `AutonomyProfileV1`; it is not inferred from behavior. The first version is
   limited to `engine.homey`, one exact target, exact resolved zone entity IDs,
   the three declared lighting routine templates, the two lighting capability
   families, local privacy and a `low` risk ceiling.
2. Wildcards are forbidden in the stored profile. Plugin manifest fingerprint,
   target identity and entity identities are frozen at enrollment.
3. Fixed maximums are: owner-selected brightness, at most 20 W, at least five
   minutes cooldown, at most six actions per zone per hour and thirty total per
   hour. A plugin compiler may tighten these values, never widen them.
4. Only a candidate that passed ADR-0004 real shadow may auto-promote. Promotion
   atomically stores the exact RoutineSpec, GoalSpec and derived submandate.
5. A submandate is exact and lasts 24 hours. Heart may renew the same scoped
   submandate while profile, manifest, target, entities and limits remain
   unchanged. Renewal is not new enrollment.
6. `engine yolo disable` persists profile revocation, suspends linked routines
   and revokes derived mandates in one store transaction. Policy therefore sees
   revocation immediately.
7. Manifest drift, missing entities, higher risk, capability expansion, profile
   disable, lost runtime lease, Homey observe mode, missing
   `ENGINE_HOMEY_ARMED=1`, stale evidence or missing oracle evidence stops the
   path. Homey's allowlist and process arming remain independent gates.
8. A new routine inside this envelope is delegated system authorization, not
   model authorization. Gemma or another model may describe/rank candidates;
   it cannot declare templates, create profiles, mint mandates or certify
   effects.
9. External opposite changes own the actuator for two hours. An explicit owner
   correction, or three contradictory external changes within seven days,
   atomically rolls back the routine, linked goal and mandate.

## Alternatives considered

### Treat five repeated actions as owner consent

Rejected. Observation and authorization are constitutionally separate.

### Give the learner a broad Homey standing mandate

Rejected. It would permit device/capability expansion and make the compiler an
authority source.

### Renew by creating broader or longer mandates

Rejected. Renewal must retain the exact original scope; any expansion requires a
new owner enrollment.

## Consequences

YOLO is intentionally narrow and persistent until explicit disable. It grants
choice among proven static templates inside an owner envelope, not unrestricted
home automation. More zones require new enrollment. Switches, covers and climate
remain outside this tranche even though older explicit GoalSpecs may still use
their existing contracts.

## Safety and scientific impact

The authority gate is testable independently from model availability. Fake
tests cover scope/risk/limit expansion, revocation and Homey kill switches. No
live Homey mutation or physical-safety claim is established by this ADR.

## Migration

No profile is created automatically. Existing standing mandates and goals remain
unchanged. Candidate evidence remains available when YOLO is disabled.

## Reversibility

Disable is immediate and durable. Exact rollback records remain in candidate and
routine state; audit receipts and negative shadow outcomes are retained.
