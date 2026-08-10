# ADR-0003 — Multi-target action lifecycle

- Status: accepted by explicit owner implementation direction
- Date: 2026-08-10
- Owner: project owner
- Scope: authoritative goal, proposal, authorization, dispatch and effect lifecycle

## Context

The v1 Heart binds one goal to one target. An executive `USE_TOOL` decision is
schema-checked and then passed to that target's `execute()`. This does not support
goals spanning Homey, local time and weather, and it does not persist first-class
proposal, policy, authorization or effect objects. Direct tool use is especially
unsuitable for physical mutations: an LLM must choose a desired effect, not an
unbounded device API or raw setpoint.

## Decision

1. `GoalSpecV2` scopes entities/targets rather than one target and binds an active
   `StandingMandateV1`. `ACHIEVE` and `MAINTAIN` retain ADR-0001 semantics.
2. Heart composes target observations into one durable `WorldSnapshotV2` at a
   logical boundary. Target revisions are monotone independently; the composed
   revision is monotone in Engine's store.
3. Events only schedule a wake. A fresh provider observation is the sole input to
   operational truth and every mutating lifecycle.
4. The cognitive decision vocabulary is `QUERY_WORLD`, `CONSULT_SPECIALIST`,
   `PROPOSE_EFFECT`, `WAIT`, `COMPLETE` and `ABANDON`. Physical mutation has no
   `USE_TOOL` fast path in v2.
5. Every mutation follows and durably records:

   ```text
   observe -> propose effect -> validate -> policy -> authorize -> dispatch
           -> observe -> reconcile -> receipt/effect
   ```

6. The general brain chooses strategy, semantic effect and specialist. A typed
   domain controller chooses exact physical parameters within the capability
   envelope. Policy and authorization are deterministic and outside all brains.
7. Authorization binds request hash, target, entity, capability, snapshot,
   parameters/limits and expiry. A request cannot carry or mint its authorization.
8. Success is established by an `EffectOracle` using a fresh post-observation.
   An ACK alone produces at most an execution fact, never goal success. Missing
   effect evidence is `UNKNOWN`.
9. Stable maintained goals make zero executive/specialist calls. A bounded local
   context projector wakes cognition on novelty, conflict, insufficient plan
   coverage or observed goal violation. A previously successful typed proposal
   may be reused only when its deterministic situation key, capability contract
   and mandate still match.
10. Targets may have independent freshness/poll intervals. Scheduled wakes,
    task handles and stream cursors are durable, though Homey initially dispatches
    only `IMMEDIATE` requests.
11. Deny-by-default policy is mandatory. High-risk or unarmed families return
    `REQUIRE_APPROVAL` or `DENY`; a standing mandate can remove per-action approval
    only inside its exact enrolled scope.

## Alternatives considered

### Keep `USE_TOOL` and add a mandate argument

Rejected. It lets proposal and exact command collapse into one model-controlled
object and cannot prove independent authority or post-effect reconciliation.

### Put multi-target aggregation in Homey

Rejected. Time/weather and future worlds would become Homey application state,
and a non-house plugin would require another Heart architecture.

### Call the model on every poll

Rejected. It wastes compute and moves deliberation toward the realtime path.

## Consequences

The mutation path has more durable records and explicit terminal states. This is
intentional audit state, not conversational memory. The existing v1 proof remains
available, while physical autonomy uses the stricter v2 path. Recovery can inspect
exactly which stage was reached without blindly duplicating effects.

## Safety and scientific impact

Malformed, stale, denied and out-of-mandate proposals cannot reach dispatch.
Prediction remains separate from observed effect. Zero modelcalls while stable,
ACK-without-effect failure, restart continuity and cross-world reuse become
executable acceptance gates.

## Migration

V1 goals are copied into v2 with a target selector and their existing success
specification as a deterministic condition input. No v1 authorization is inferred.
Existing target adapters remain observe-only until wrapped by v2 roles.

## Reversibility

The additive runtime can be disabled while preserving its ledger. Re-enabling it
reconstructs from v2 snapshots and lifecycle records. Removing the lifecycle
requires a superseding ADR because proposal/authority separation is constitutional.

