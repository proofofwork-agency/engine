---
title: All modes and statuses
sidebar_position: 5
description: Engine taxonomies for autonomy, goals, cognition, invocation, policy, evidence, learning, routines, and Homey.
---

# All modes and statuses

“Mode” is often used conversationally for several different things. Engine keeps them separate: goal behavior, cognitive decisions, invocation duration, execution status, control layer, risk, privacy, policy, evidence, learning, routines, and a plugin kill switch are distinct axes.

> **Status:** action lifecycle values remain v2 contracts; generic autonomy uses
> `engine.plugin/v3`. Values below are current unless marked legacy or roadmap.

## 1. Goal mode: `GoalModeV2`

| Value | Meaning | End behavior |
| --- | --- | --- |
| `achieve` | Reach the desired effect once | Observed true -> `completed` |
| `maintain` | Keep the desired effect true over time | Observed true -> `monitoring`; drift -> active again |

Both **exist now**. `maintain` is not a realtime mode: detection latency depends on events, polling, and provider freshness.

## 2. Persistent goal status

In the current implementation, this is a set of stored strings, not a separate public SDK enum.

| Status | Meaning |
| --- | --- |
| `active` | The goal needs another pass |
| `completed` | An `ACHIEVE` goal has independently been established as true |
| `monitoring` | A `MAINTAIN` goal is true and remains under observation |
| `waiting` | Waiting for change, approval, a task poll, or another resume condition |
| `uncertain` | Required evidence or the oracle is `UNKNOWN`; do not treat it as false or success |
| `degraded` | An isolated goal/provider/brain route failed or exhausted its budget/circuit |
| `abandoned` | A stop condition or explicit abandonment ended the goal |

A `COMPLETE` brain decision does not directly set `completed`; the Heart does so only after condition/oracle evaluation.

## 3. Cognitive decision: `DecisionKindV2`

| Value | Intent | Authority/effect |
| --- | --- | --- |
| `query_world` | More or different observation is needed | No mutation; the current Heart waits/re-observes |
| `consult_specialist` | Invoke a named specialist | Specialist advice remains a proposal |
| `propose_effect` | Return a semantic `ProposedActionV1` | Still no execution rights |
| `wait` | Do nothing now and wait for relevant change | Durable `waiting` |
| `complete` | The brain thinks the work is complete | Advisory only; oracle/conditions decide |
| `abandon` | Advise leaving the goal | Heart may record status `abandoned` |

The v1 terms `CONSULT_BRAIN` and `USE_TOOL` are legacy. V2 deliberately has no physical `USE_TOOL` fast path: proposals always pass through controller, policy, authorization, executor, and oracle.

## 4. Invocation mode: `InvocationModeV2`

| Value | Semantics | Implementation status |
| --- | --- | --- |
| `immediate` | Dispatch returns a terminal receipt or a result that can be reconciled immediately | **Implemented** and **Fake/simulation-tested**; used by Homey |
| `task` | Dispatch returns an external handle; Heart polls, cancels at deadline, and reconstructs after restart | **Implemented** and **Fake/simulation-tested** in the reference warehouse |
| `stream` | Long-running stream with cursor/reconnect semantics | **Contract/store scaffolding**; no end-to-end reference proof yet |

Invocation mode describes the duration of a capability, not goal duration, risk, or autonomy.

## 5. Execution status: `ExecutionStateV2`

| Status | Terminal? | Meaning |
| --- | --- | --- |
| `requested` | No | The request has been created/recorded |
| `accepted` | No | An external executor accepted it; a handle is required for task recovery |
| `running` | No | Execution is in progress; a handle is required |
| `succeeded` | Yes | Executor reports successful execution; the effect still requires independent verification |
| `partial` | Yes | Only part was executed or achieved |
| `failed` | Yes | Executor reports failure |
| `cancelled` | Yes | Task was cancelled |
| `unknown` | Yes | The lifecycle cannot reliably determine execution/acknowledgement |

`succeeded` therefore means “the execution receipt succeeded,” not automatically “the goal effect was achieved.” The latter appears in `EffectDeltaV1` and fresh goal evaluation.

## 6. Control layer: `ControlLayer`

| Value | Use |
| --- | --- |
| `query` | Observe/query; an `opaque` capability must be query-only |
| `semantic` | High-level domain effect translated by a controller into target parameters |
| `actuator` | Capability is closer to an actuator but remains outside hard-realtime control |

A control layer grants no permission and does not determine the risk class by itself.

## 7. Risk class: `RiskClass`

| Value | Interpretation |
| --- | --- |
| `read_only` | No intended world mutation |
| `low` | Bounded low-risk action within enrolled limits |
| `medium` | Higher impact; policy/mandate must carry it explicitly |
| `high` | Current policy requires approval unless the mandate explicitly allows it |

This is a software taxonomy, not certification. A misclassified capability does not become physically safe because its manifest says `low`.

## 8. Privacy class: `PrivacyClass`

| Value | Meaning |
| --- | --- |
| `public` | Public information |
| `local` | Local operational data |
| `sensitive` | Explicit privacy permission required |
| `camera` | Camera/image data; explicit permission required |

A remote model does not automatically receive all observations. Context projection and plugin needs remain separate boundaries.

## 9. Policy outcome: `PolicyOutcome`

| Value | Consequence |
| --- | --- |
| `ALLOW` | Policy may create an exactly bound authorization |
| `DENY` | Final refusal for this request/state binding |
| `REQUIRE_APPROVAL` | An external authorized approval is required; a brain cannot provide it |
| `DEFER` | Not yet decidable/active, for example because a mandate is not yet valid |

Only `ALLOW` reaches dispatch.

## 10. Evidence grade: `EvidenceGrade`

| Value | Meaning |
| --- | --- |
| `OBSERVED` | Emitted directly by an identified sensor/tool/executor within its coverage |
| `DERIVED` | Deterministically derived from named observations |
| `INFERRED` | Model or statistical conclusion |
| `UNKNOWN` | Insufficient evidence |
| `CONFLICTING` | Sources disagree |
| `STALE` | Evidence is too old for this decision |

Confidence and provenance remain separate from the grade. High confidence does not turn `INFERRED` into `OBSERVED`.

## 11. Preference promotion: `PreferencePromotionMode`

| Value | Meaning |
| --- | --- |
| `explicit_only` | Only an explicit owner correction may change the preference |
| `shadow_low_risk` | Inferred evidence may enter a candidate/shadow route after fixed gates |

This changes preference state, not model weights or authority scope.

## 12. Preference learning status: `LearningStatus`

| Status | Meaning |
| --- | --- |
| `candidate` | A candidate has been identified |
| `shadow` | Evaluation period without direct authority expansion |
| `promoted` | A new versioned GoalSpec preference is active |
| `rejected` | Gates or outcomes did not pass |
| `rolled_back` | The exact old value was restored in a new version |

In practice, the current generic route starts at `shadow` once the evidence gates pass; `candidate` remains a public contract status.

## 13. Routine candidate status: `RoutineCandidateStatus`

| Status | Meaning |
| --- | --- |
| `candidate` | Pattern candidate |
| `shadow` | Counterfactual test; dispatch count must remain zero |
| `ready_for_approval` | Real shadow opportunities and the agreement gate passed; owner approval is required |
| `promoted` | Routine, goal, and mandate were activated atomically |
| `rejected` | Pattern/conflict/shadow failed |
| `rolled_back` | Promotion was exactly reversed |

## 14. Active routine status: `RoutineStatus`

| Status | Meaning |
| --- | --- |
| `shadow` | Routine exists inertly during evaluation |
| `ready_for_approval` | Ready for explicit activation |
| `active` | Guard and authority permit evaluation/goal execution |
| `dormant` | Guard false, cooldown active, recurrence already handled, or override active |
| `guard_uncertain` | Guard contains `UNKNOWN`, `STALE`, or `CONFLICTING`; fail-closed |
| `conflicted` | An opposing routine blocks or wins on priority |
| `suspended` | Authority, rate, manifest, or another hard gate fails |
| `rejected` | Routine was rejected |
| `rolled_back` | Routine, linked goal, and mandate were rolled back |

## 15. Global autonomy mode: `AutonomyModeV1`

| Mode | Meaning |
| --- | --- |
| `observe` | Run enrolled strategies as durable shadow; dispatch count is exactly zero |
| `supervised` | Persist proposals for owner approval; approval reobserves and reevaluates before dispatch |
| `delegated` | Permit enabled exact enrollments to instantiate templates and execute at most low-risk work |
| `paused` | Continue observation, learning, and in-flight recovery; start no strategy, brain, or dispatch work |

Mode is global and revisioned by an epoch. It grants no target authority by
itself. An enabled `AutonomyEnrollmentV2` separately freezes exact strategy,
templates, targets, entities, capabilities, context/privacy, cognition route,
limits, budget, expiry, privileges, and fingerprints.

`yolo` is only a CLI alias: enable selects `delegated`, disable selects `paused`,
and status shows generic autonomy status. It creates no enrollment. Legacy
`AutonomyProfileV1` rows remain audit data and grant no v3 authority. See
[Generic plugin autonomy](./plugin-autonomy.md).

## 16. Autonomy decision and cognition route

An `AutonomyDecisionV1` is one of `NOOP`, `DEFER`, `PROPOSE_EFFECT`,
`PROPOSE_GOAL_CANDIDATE`, `REQUEST_EXECUTIVE`, or `REQUEST_SPECIALIST`.
`deterministic` makes zero brain calls; `executive` and `specialist` admit only
their declared destination; `hybrid` runs the strategy first and admits at most
one requested cognition call. None of these decisions is authority.

## 17. Homey transport mode

The Homey plugin also has an operational configuration value:

| Mode | Behavior |
| --- | --- |
| `observe` | Read-only; recommended starting point |
| `act` | The mutation path may open, but only together with `ENGINE_HOMEY_ARMED=1`, allowlists, fresh state, mandate, policy, and request-bound authorization |

`act` is therefore only a transport kill switch. It bypasses no Engine policy. Do not confuse `observe`/`act` with `ACHIEVE`/`MAINTAIN` or `IMMEDIATE`/`TASK`/`STREAM`.

## 18. CLI preview versus activation

`engine setup` is preview-only by default. `--activate` writes the goal and mandate. This is a mutation choice in the CLI, not a persistent runtime mode.

## Legacy v1

V1 contains corresponding goal, invocation, and receipt values, plus `Affordance` (`query`, `action`, `event`). New product features use v2. The v2 registry projects v1 plugins as observe-only, so a v1 action affordance grants no v2 mutation rights.

See [Architecture](./architecture.md) for the sequence in which these axes come together and [How Engine learns](./learning.md) for the learning gates behind the statuses.
