# ADR-0009 — Lease-fenced crash-safe dispatch and resource conflicts

- Status: accepted by explicit owner implementation direction
- Owner: project owner
- Date: 2026-08-11

## Context

An authorization can become invalid between policy evaluation and executor I/O.
A process can also crash after an external effect but before storing its
receipt. Retrying blindly can duplicate physical or business effects. Heart must
reconstruct enough durable intent to recover without treating absence of a
receipt as proof that nothing happened.

## Decision

1. Runtime leases carry a monotonically increasing generation. Every dispatch
   uses that fencing token and verifies owner, generation, and expiry immediately
   before external I/O. Mode changes remain available through the store while a
   runtime owns the active lease.
2. Before dispatch, Heart stores a `DispatchAttemptV1` in `PREPARED` with a
   stable operation key plus request, target, entity, conflict domain, lease
   generation, authorization expiry, and autonomy binding.
3. After a restart Heart observes first. A `PREPARED` attempt becomes
   `RECOVERY_REQUIRED`; it is never automatically redispatched. A terminal
   receipt and fresh oracle evidence can close the attempt. Non-terminal task
   receipts remain reserved and use the existing poll/cancel recovery path.
4. Immediately before dispatch Heart rechecks current mode epoch, enabled
   enrollment revision and expiry, all fingerprints, request hash,
   authorization expiry, resource reservation, and the live lease fence.
   Failure causes zero executor calls.
5. Each mutating v3 capability declares a generic `conflict_domain`. Enabled
   enrollments with overlapping `(target, entity, conflict_domain)` resources
   are rejected. An open dispatch attempt reserves the same resource.
6. Recovery is allowed after pause, enrollment disable, or revocation because
   observing and reconciling an already possible effect is not a new mutation.
   Polling or cancellation still uses the current fenced lifecycle; Engine does
   not invent success for a recovery action.
7. Schema additions and the lease-column migration are transactional. Stored
   mode, enrollments, evaluations, bindings, attempts, and in-flight tasks are
   reconstructible without a model session.

## Alternatives

- Retry any missing receipt using the request idempotency key: rejected because
  a declared key does not prove every target honored it before a crash.
- Hold resource ownership only in memory: rejected because restart would erase
  the reservation.
- Treat an executor ACK or tool result as the effect oracle: rejected because
  execution acknowledgement is not observation of the requested outcome.
- Cancel all work on pause/revocation: rejected because cancellation itself may
  mutate a target and its success still needs observation.

## Consequences

Ambiguous attempts can require operator reconciliation rather than automatic
progress. This is intentionally conservative. The v1 scheduler uses exclusive
resource enrollment rather than priority/preemption arbitration. Stable
operation keys and durable attempts make crash injection testable and prevent
blind redispatch on restart.

## Safety and scientific impact

Lease ownership is coordination, not physical safety. Fencing narrows the
window for concurrent/stale dispatch but does not certify a target, network, or
executor. An unresolved attempt remains `UNKNOWN`/recovery-required until fresh
evidence covers it. Simulation-based exactly-once tests do not prove real-world
exactly-once behavior for a target whose idempotency semantics are unknown.

## Migration and reversibility

Existing SQLite stores gain the new tables and lease generation column without
deleting v1/v2 lifecycle data. The migration runs in a transaction and advances
the world schema version. Removing this behavior safely requires draining or
explicitly resolving every open attempt first; otherwise the old runtime could
redispatch work whose external outcome remains ambiguous.
