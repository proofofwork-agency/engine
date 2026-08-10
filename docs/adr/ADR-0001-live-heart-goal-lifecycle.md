# ADR-0001 — Live Heart and maintained-goal lifecycle

- Status: accepted by explicit owner direction
- Date: 2026-08-10
- Owner: project owner
- Scope: authoritative goal lifecycle and deliberative/realtime boundary

## Context

Engine 0.1 could autonomously run an active goal to completion and reconstruct it
after process restart. Its public story overemphasised restart, however, while a
completed goal was no longer observed. `WAIT` also returned to the hot cognition
loop, so a waiting model could consume its budget without a world change.

That behavior is insufficient for the owner concept: Engine is a living Heart
that keeps goals, state, attention and cognition alive. Process restart is a
continuity fault test, not Engine's normal operating cycle.

At the same time, Engine's LLM/planner may not enter hard-realtime device loops.
Events are not authoritative observations, and stable targets must not cause
continuous model calls.

## Decision

1. Goals declare one of two durable modes:
   - `ACHIEVE`: reach the target oracle once, then become `completed`;
   - `MAINTAIN`: keep the oracle true over time and remain live.
2. A satisfied maintained goal enters `monitoring`, not `completed`.
3. `LiveEngine` runs until explicitly stopped. It fairly advances active goals,
   observes quiet goals, waits when there is no cognition to run, and wakes from
   either target events or a configurable poll fallback.
4. Target events are wake-up hints only. Heart always calls `observe()` and the
   target oracle before reasoning or acting.
5. Stable monitoring performs no executive or specialist brain call. Cognition
   wakes only when observed state no longer satisfies the maintained goal.
6. `WAIT` changes the durable goal to `waiting`; unchanged observations do not
   invoke the brain again. A goal-relevant changed observation wakes the goal;
   adapters may filter unrelated telemetry through a typed optional seam.
7. A maintained goal's cycle budget applies per repair intervention. Exhaustion
   changes it to `degraded`, which remains observable and can wake on later state
   change; it does not masquerade as successful completion.
8. Hard-realtime stabilization, motor control, flight control and equivalent
   loops stay in target-specific controllers. `LiveEngine` is an always-on
   deliberative/event loop, not a hard-realtime controller.
9. Process restart remains supported and tested, but is secondary recovery
   evidence rather than the primary product narrative.
10. An unavailable or invalid target oracle moves the goal to `uncertain` and
    blocks cognition/action until exact boolean truth returns. Recovery remembers
    whether a relevant change occurred while truth was unavailable.
11. Brain/provider failures use persisted exponential backoff. Repeated failures
    open a `degraded` circuit that is retried only after its durable delay. Retry
    state clears only when the failed brain/stage actually succeeds or the goal is
    independently resolved; an unrelated oracle-unknown pass is not recovery.
12. When `run_forever()` is launched from another thread, it uses a thread-local
    SQLite connection and closes it plus all subscriptions on exit.

## Alternatives considered

### Keep only run-to-completion plus restart

Rejected. This makes Engine look like a durable workflow runner and cannot
represent a continuing desired state.

### Poll every target through an LLM continuously

Rejected. It wastes context/compute, creates latency, and improperly moves a
model toward the realtime path. Deterministic observation and oracles are the
cheap monitoring layer.

### Treat every adapter event as authoritative state

Rejected. An event may be delayed, duplicated, incomplete or wrong. It may wake
Heart, but only a versioned observation can update operational truth.

### Require every adapter to implement subscriptions immediately

Rejected for the alpha kernel. Subscriptions are an optional seam and polling is
the compatibility fallback. Future provider contracts may make event/QoS support
explicit per target.

## Consequences

### Positive

- Engine now has a literal live operating mode rather than only a restart story.
- Desired-state use cases (home, ops, browser sessions, devices) have an explicit
  lifecycle.
- Stable state does not spin the LLM or consume cognitive cycles.
- Missing oracle truth cannot fall through into model/tool execution.
- Provider outages are rate-limited durably instead of producing a hot retry loop.
- Drift, waiting, degradation and recovery are durable, auditable events.
- Existing one-shot goals remain source-compatible through the `ACHIEVE` default.

### Costs and limitations

- Polling frequency trades detection latency for observation cost.
- The current scheduler is single-process and cooperative, not distributed.
- Adapter event delivery, task/stream actions and reconnect semantics remain
  alpha gaps.
- `MAINTAIN` does not make a target safe; policy, authorization and device safety
  boundaries remain separately required where risk warrants them.

## Safety and scientific impact

- The decision strengthens `missing != false`: oracle failures remain unknown and
  do not certify success or trigger model action solely as if failure were known.
- Events remain separate from observations.
- Hard-realtime control remains outside LLM/planner authority.
- New tests must establish no idle model spin, autonomous drift repair, quiet
  `WAIT`, lifecycle migration, and event/poll wake behavior.

## Migration

Existing SQLite goal tables receive:

- `mode TEXT NOT NULL DEFAULT 'achieve'`;
- `intervention_cycle INTEGER NOT NULL DEFAULT 0`.

Existing goals therefore retain one-shot semantics. New maintained behavior is
opt-in with `Goal(mode=GoalMode.MAINTAIN)`.

## Reversibility

The runtime driver is additive and can be stopped without changing target state.
One-shot goals are unchanged. Removing maintained goals later would require an
explicit migration for nonterminal `monitoring`, `waiting` and `degraded` rows;
therefore such removal needs a superseding ADR.
