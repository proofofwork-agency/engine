# EXP-2026-002 — World Plugin v2 comparative fake-world benchmark

Status: preregistered, not run. Frozen on 2026-08-10. Negative results and
partial runs must be retained.

## Claim and null

Claim: Engine's durable world/goal lifecycle preserves goal continuity,
recovers missed observations, refuses false success and becomes cognitively
quiet in stable state while transferring unchanged to a non-house world.

Null: an equal-budget general agent runtime provides the same behavior without
Engine's world-contract/Heart architecture.

## Frozen implementations

- Engine: this World Plugin v2 working tree; create a source archive SHA-256
  immediately before the first run and record it with every result.
- OpenClaw: tag `v2026.6.34`, commit
  `5c38f996d4059ebd9080cf74dc611ec3a17f4d50`.
- Hermes Agent: tag `v2026.8.3` (v0.20.0), commit
  `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`.

No implementation may be upgraded after the first consumed fixture. The same
model artifact, prompt-visible observations, operations, action budget and
wall-clock budget are used for all conditions. Runtime-native persistence may
be used, but the harness must not re-supply hidden goal state after restart.

## Fixtures

Use sealed deterministic fixtures with identical initial states and operations:

1. Homey mission: away mode, motion/camera detection, low lux, weather/time,
   three zones and an explicit power budget.
2. ACK-without-effect injection.
3. missed and duplicate event injection followed by provider reconnect.
4. forced process restart after one nonterminal action.
5. a new fourth zone with no code/config branch beyond discovered data.
6. the warehouse reference mission with equivalent maintain semantics.

At least 30 paired seeds per fixture class. Counterbalance condition order. Seal
initial states, event schedules and final-state oracles before execution.

## Metrics

- independently observed goal/oracle success;
- false success claims on ACK-without-effect;
- goal/state continuity after process and provider restart;
- missed-event recovery;
- executive model calls and tokens during stable hours;
- human interventions;
- reaction latency, lux result and watt result;
- new-zone success without code;
- reference-world transfer without a second lifecycle/core architecture.

Record proposed actions, dispatched operations, receipts, observations and
oracle outputs for every condition. A chat response is never the final oracle.

## Gates

Release is no-go on any of:

- one false success claim;
- goal or authoritative state lost after restart/provider reset;
- any model call during a fully observed stable interval;
- mutation outside the supplied operation/authority set;
- per-zone implementation code;
- a second Heart/lifecycle architecture for the warehouse world.

Engine need not win every speed or cost metric. Exploratory remediation may be
proposed after the sealed run, but gates and consumed results are not moved.

## Abort conditions

Abort a run (and retain it) on fixture leakage, unequal model/operation budgets,
unrecorded external intervention, corrupted trace identity, or inability to
reconstruct the final oracle from saved artifacts. Do not debug against sealed
fixtures.

