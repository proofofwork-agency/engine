# ADR-0013 — Dispatch admission serialization and attempt closure

- Status: proposed. Partial implementation may land in slices; owner
  signature is required before any live act (C5/D2).
- Owner: project owner
- Date: 2026-08-14

## Context

Before a live SUPERVISED Homey action, admission must be serializable with
mode changes, enrollments must not accept unenforceable budgets, and an
ambiguous attempt must not deadlock a zone.

## Decision

1. Final admission gates and the `PREPARED` write run in one
   `BEGIN IMMEDIATE` transaction. A mode change invalidates future
   admissions and never recalls in-flight I/O.
2. CLI `autonomy mode` and `autonomy disable` are audited and serialized
   with that transaction.
3. Enroll rejects a non-empty `budget` object. The runtime cannot honor
   it. Unenforced limit keys are rejected once the enforced set is listed
   in this ADR; until then only non-empty budget is rejected.
4. An attempt that remains ambiguous after a one-hour horizon becomes
   `CLOSED_UNKNOWN`. `engine autonomy attempts list|close` is the operator
   path. Recovery of a possible existing effect is still observation, not
   a new mutation.
5. An enrollment owns its reserved `(target, entity, conflict_domain)`. A
   live goal and an enrollment on the same zone resolve to one
   deterministic owner.

## Alternatives

- Continue accepting ignored budget keys and hope operators notice.
- Leave ambiguous attempts open indefinitely.

## Consequences

Live C5 cannot start until this ADR is accepted and the remaining
admission/closure tests are green. Partial budget rejection can land
earlier without enabling act mode.

## Safety / scientific impact

Admission serialization is an authority change. It does not replace
physical interlocks. `CLOSED_UNKNOWN` is not success.

## Migration and reversibility

New enrollments with a non-empty budget fail closed. Existing stored
enrollments are unchanged.

## Reversibility

Yes, by revert.
