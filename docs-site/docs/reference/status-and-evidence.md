---
title: Status and evidence
description: Evidence grades, lifecycle states, and the boundary between execution and effect.
sidebar_position: 1
---

# Status and evidence

Engine does not store only a final label. At every step it records what was
proposed, validated, allowed, executed, and subsequently observed. Status and
evidence are different dimensions:

- an executor may report `succeeded` while the desired effect is not observed;
- an oracle may return `achieved = null` because measurement coverage is
  missing;
- a model may sound highly confident while providing only `INFERRED` data.

## Evidence grades

| Grade | Meaning | May serve as direct operational truth? |
| --- | --- | --- |
| `OBSERVED` | Emitted directly by an identified sensor, tool, provider, or executor within its coverage | Yes, within the source, time, and coverage |
| `DERIVED` | Deterministic transformation of identified observations | Yes, if the inputs and transformation are auditable |
| `INFERRED` | Model or statistical conclusion | Not without policy/validation; never relabel it as an observation |
| `UNKNOWN` | Insufficient evidence | No; missing is not `false` |
| `CONFLICTING` | Sources disagree | No; reconcile or defer first |
| `STALE` | Evidence is too old for the decision | No, for the relevant operational decision |

`quality` or `confidence` is not a substitute for an evidence grade. A
high-confidence inference remains `INFERRED`.

## Truth is coverage-bound

Engine can establish a fact only within the current, documented coverage of an
identified observation source or effect oracle. “Fresh” does not necessarily
mean “complete.” For example:

- a device-state observation can establish that a light reports `on`, while a
  separate lux observation is needed to establish room brightness;
- an API acknowledgement can establish that a task was accepted, while fresh
  business or physical observations are needed to establish the requested
  outcome;
- a camera or presence sensor can cover one zone without saying anything about
  an uncovered zone;
- a deterministic oracle can justify `false` only when its inputs cover the
  entire condition it evaluates.

Outside that coverage the result remains `UNKNOWN`. Evidence that exceeded its
freshness contract becomes `STALE`. Sources that disagree become `CONFLICTING`.
These values block or defer claims that require certainty; a model prediction,
high confidence, API success code, or cached earlier observation cannot silently
upgrade them.

## Policy outcomes

| Outcome | Meaning |
| --- | --- |
| `ALLOW` | The exact request currently fits the mandate, capability, limits, and freshness requirements |
| `DENY` | The request is explicitly not allowed |
| `REQUIRE_APPROVAL` | A human approval boundary is required |
| `DEFER` | The available information is currently insufficient or unsafe for a decision |

Only `ALLOW` can yield an `AuthorizationV1` in the current Heart. That
authorization binds to the request hash, request, target, entity, capability,
parameter limits, snapshot, mandate, and expiry.

## Execution receipt states

| State | Meaning |
| --- | --- |
| `requested` | The request was submitted but has not yet been accepted |
| `accepted` | The target accepted a non-terminal task |
| `running` | The task is running |
| `succeeded` | The executor reports successful terminal execution |
| `partial` | Only part of the request was executed |
| `failed` | The executor reports a terminal error |
| `cancelled` | The task was cancelled |
| `unknown` | The outcome cannot be established reliably |

`succeeded` is an execution state. Goal success follows only from a fresh
post-observation and an `EffectDeltaV1`. If an exception occurs around dispatch,
the Heart stores an `unknown` receipt instead of assuming that nothing happened;
dispatching again could duplicate a physical effect.

Before external I/O the v3 Heart persists a `DispatchAttemptV1` with a stable
operation key, lease generation, authorization expiry, resource identity, and
autonomy binding. After a crash, a still-prepared attempt becomes
`RECOVERY_REQUIRED`: Heart observes first and never blindly redispatches it.

## `EffectDeltaV1`

An effect delta binds:

- goal, proposal, request, and receipt;
- pre- and post-snapshot;
- evidence grade;
- `achieved: true | false | null`;
- measured changes and observation IDs;
- reason and observation time.

`true` means that the plugin oracle confirmed the effect in the fresh post-state
within its documented coverage. `false` means that sufficient coverage justifies
a negative result. `null` means unknown, not silently failed or succeeded.

## Goal states in the v2 Heart

Goal status is currently a stored string, not a public enum. The canonical v2
path uses these values:

| Status | When |
| --- | --- |
| `active` | The goal still has effects that have not been demonstrated and may continue working |
| `monitoring` | A `maintain` goal is currently demonstrably stable |
| `completed` | An `achieve` goal is demonstrably achieved |
| `waiting` | The brain deferred or waited, policy blocked, or a task is running |
| `uncertain` | Required evidence or task identity is unknown |
| `abandoned` | A stop condition or explicit brain decision ends the goal |
| `degraded` | The living loop isolated a goal failure and remains available to other goals |

A stable `monitoring` goal makes zero executive and specialist calls. After
drift, it may re-enter the existing lifecycle.

## Learning states

Preference candidates use:

| Status | Meaning |
| --- | --- |
| `candidate` | Evidence collected; the gate has not yet passed |
| `shadow` | Counterfactual evaluation without dispatch |
| `promoted` | A new GoalSpec version was stored |
| `rejected` | The candidate was rejected explicitly or because of conflict |
| `rolled_back` | An earlier promotion was reversed through a stored patch |

Routine candidates use `candidate`, `shadow`, `ready_for_approval`, `promoted`,
`rejected`, and `rolled_back`. A demonstrated candidate is promoted automatically
only with a matching exact low-risk autonomy profile; otherwise it stops at
`ready_for_approval`.

Active routines use:

| Status | Meaning |
| --- | --- |
| `shadow` | Still exclusively counterfactual |
| `ready_for_approval` | Gates passed; owner approval is missing |
| `active` | The guard may activate the linked GoalSpec |
| `dormant` | The guard is demonstrably false, or recurrence/cooldown blocks it |
| `guard_uncertain` | Guard evidence is unknown, stale, or conflicting |
| `conflicted` | An equivalent opposing routine blocks deterministically |
| `suspended` | Authority, profile, manifest, or limit is no longer valid |
| `rejected` | The candidate or routine was rejected |
| `rolled_back` | The routine, goal, and sub-mandate were reversed/revoked exactly |

## Generic autonomy states

The global mode is `observe`, `supervised`, `delegated`, or `paused` and carries
a monotonically increasing epoch. Enrollment revisions are separate. Durable
proposal bindings use `shadow`, `pending_approval`, `approved`, `dispatched`,
`rejected`, `deferred`, or `superseded`.

`shadow` means zero dispatch. `pending_approval` is not frozen authority:
approval first reobserves and reruns the strategy. Only a fresh matching
proposal can become approved. Autonomous dispatch requires current delegated
mode plus an enabled exact enrollment; supervised dispatch requires the explicit
owner approval route. In both cases current mode/enrollment, fingerprints,
lease fence, request hash, and authorization expiry are checked again before
executor I/O.

## Snapshot and provenance

`TargetObservationV2` has a target revision. `WorldSnapshotV2` stores that
revision per target and adds an Engine-wide monotonic revision. The SHA-256 of
canonical data identifies the artifact. A model receives only a bounded context
projection; the complete snapshot remains local operational state.

Plan-cache reuse requires a matching goal version, effect selector, manifest
fingerprint, and mandate. A changed manifest or authority scope therefore does
not make an earlier success valid automatically.

## What the repository currently demonstrates

The current deterministic tests and reference plugins cover, among other things:

- static/dynamic manifest comparison;
- multi-target snapshots and reconstruction after restart;
- proposal → request → policy → authorization → receipt → post-observe → oracle;
- an ACK without an effect;
- task polling/cancellation and recovery after process restart;
- exactly-once experience import and bounded learning;
- routine guards, shadow without dispatch, conflict, and rollback;
- bounded, post-persistence lifecycle observers whose delivery failures are isolated and non-authoritative;
- v3 manifest/runtime conformance for empty and non-empty autonomy roles;
- observe shadow, supervised reapproval, delegated template instantiation, and paused recovery;
- deterministic zero-brain routing plus bounded single-hop cognition failure/defer;
- enrollment overlap rejection, in-flight resource reservation, lease/revocation/expiry pre-I/O gates, and crash-no-redispatch reconstruction;
- the same generic autonomous route with Homey lighting and warehouse reserve semantics and no target identity in core autonomy modules;
- one executive interface with deterministic and model-backed implementations.

This is software and simulation evidence. The repository does not thereby claim
universal safety, certification, or a physically safe state.

## Open evidence and product gaps

- No general plugin marketplace or automatic trust/distribution chain.
- No enforced cryptographic signing of plugin artifacts.
- No general OS/process/network sandbox that enforces manifest needs.
- `stream` has contract/store scaffolding but no end-to-end reference proof.
- No multi-executive runtime; one application selects one executive.
- The preregistered, repeated physical Homey lux/watt gate has not been replaced
  by the software tests.
