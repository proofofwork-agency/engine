---
title: How Engine learns — and does not learn
sidebar_position: 6
description: The distinction between state, experience, preferences, routines, plan reuse, and future model weights.
---

# How Engine learns — and does not learn

Engine does not use “learning” as an umbrella term for every state change. The current implementation adapts durable preferences and routines through fixed evidence gates. It does not train model weights and does not turn observation or repeated behavior into authorization.

> **Status:** explicit corrections, plugin-neutral behavior import, preference candidates, routine shadowing, GoalSpec versioning, and rollback **exist now** and have been tested with fakes/reference worlds. Online weight training and automatically created mini-brains are **roadmap**.

## Five things that remain separate

| Concept | Meaning | Example |
| --- | --- | --- |
| **State** | Current target facts, goals, and beliefs at a logical observation boundary | Light is off; warehouse bin contains two crates |
| **Experience** | Historical actions, receipts, effects, corrections, and outcomes | This route ended partial; this setting changed externally five times |
| **Preferences/routines** | Versioned operational configuration derived through explicit or gated evidence | Desired reserve band; daily “off” routine |
| **Weights** | Trained model parameters in a versioned artifact | A future vision or motion model |
| **Context projection** | Temporary, bounded input for a brain call | Only entities and observations around this goal |

A state change requires no training. A preference promotion is not a new neural model. A new model artifact is not current world state.

## How experience is already used

Engine has several distinct mechanisms that are sometimes loosely called “learning.”

### 1. Experience changes later routing

The original 0.1 fixtures record observed effects and specialist outcomes. A negative specialist outcome can change the next specialist selection after restart. The grid world uses an observed obstacle to replan.

**Tested in simulation.** This is a transparent heuristic/state reducer, not weight training.

### 2. Observed successful plans can be reused

V2 can cache an exactly typed plan when an effect oracle has established `achieved: true`. Reuse requires the same goal version, situation key, capability manifest fingerprint, and mandate. A known situation can therefore be handled without another model call.

**Exists now.** This is deterministic memoization of observed success, not generalization to arbitrary new situations.

### 3. Explicit owner corrections

An explicit correction becomes `OBSERVED` preference evidence, is validated against the namespaced `PreferenceSpecV1`, and is written directly into a new `GoalSpecV2` version. The old version and value remain auditable.

**Exists now.** A correction may only change an already declared preference; it adds no target, capability, or mandate.

### 4. Inferred preference adaptation

A plugin may publish cursor-based `BehaviorBatchV1` signals through an optional `ExperienceProvider`. The Heart:

1. validates provider and plugin identity;
2. stores signals exactly once with a durable cursor;
3. checks the declared preference and value schema;
4. links only when plugin, target, entity, capability, selector, and preference match an active goal;
5. preserves unknown signals as unlinked evidence instead of discarding them or granting authority.

An unexplained external change remains `INFERRED`: the system does not know whether a person, Flow, another integration, or chance caused it.

## Preference gates

A `shadow_low_risk` preference candidate requires at least:

- five equivalent examples;
- spread across at least three UTC dates;
- at least 80% value consistency;
- at least 80% context consistency;
- no explicit conflict;
- an active mandate with `learning.low-risk`;
- exact plugin, target, entity, and capability scope;
- a shadow period of at least seven days.

On promotion, Engine creates a new `GoalSpecV2` version, preserves evidence and outcomes, invalidates relevant plan reuse, and keeps an exact rollback patch.

### Important evidence boundary

The current preference-only code uses an evidence-consistency outcome after the fixed shadow period. That is enough to test the versioning and rollback route, but not to claim that a physical preference causes better effects. Where a preference affects execution or a physical effect, independently observed outcome evidence remains a required later product gate.

This nuance prevents “the user often did this” from being renamed “Engine knows this works better.”

## Routine learning

Routines have a stronger counterfactual shadow route. Plugins declare static `RoutineTemplateSpecV1` templates and a deterministic `RoutineCompiler`. Core interprets only generic guard, recurrence, conflict, and lifecycle contracts.

The pipeline is:

```text
plugin behavior signals
  -> fixed evidence gates (5 examples, 3 days, 80%)
  -> compiled inert RoutineSpec + GoalSpec
  -> at least 7 days of shadow, without dispatch
  -> only real trigger opportunities count
  -> at least 3 closed opportunities
  -> at least 80% later observed agreement
  -> ready_for_approval OR auto-promotion inside exact YOLO profile
  -> active routine + goal + mandate
  -> observe/act/oracle through the normal v2 lifecycle
```

A missing opportunity does not count as agreement. An uncertain guard fails closed. Conflicts, cooldowns, recurrence, and rate limits are deterministic and durable.

## Normal promotion and bounded YOLO

Without an autonomy profile, a successful routine can only become `ready_for_approval`. The owner activates it explicitly.

With `engine yolo enable`, the owner delegates a narrow Homey lighting envelope in advance. Automatic promotion is allowed only after the same shadow gates and cannot expand scope. The profile freezes exact entities, templates, capability families, manifest fingerprint, risk ceiling, and limits. Derived mandates last 24 hours and may only be renewed exactly.

An external opposing change temporarily receives actuator ownership. An explicit conflict, or three opposing changes within seven days, rolls back the routine, linked goal, and mandate.

This route is **fake-tested**, not physically certified.

## What Engine does not learn

The current Engine:

- does not train a foundation model;
- does not fine-tune the general brain online;
- does not change weights on an edge device;
- does not create new plugin families automatically;
- does not infer permission from repetition;
- does not widen targets, entities, risk, privacy, or mandate duration;
- does not call a model prediction an observation;
- does not use embeddings or free-form descriptions as canonical identities;
- does not autonomously write code or skills into the production runtime.

## Can Engine “learn” a new device?

Only within an already declared contract. A provider may discover new instances of an enrolled capability family. The plugin then supplies the entity, observations, and exact family binding. A completely unknown family becomes `opaque`, `QUERY`, and read-only.

Mutation of a genuinely new device type requires:

- a versioned plugin manifest;
- schemas, units, risk/privacy, and limits;
- controller, executor, and effect oracle;
- a fake/simulator and conformance evidence;
- explicit enrollment/mandate;
- where relevant, a target controller and independent safety plane.

That is plugin development, not silent online learning.

## Future mini-brains

A mini-brain is an optional specialist, for example for perception, anomaly detection, route selection, or a control residual. It receives no authority of its own and must never replace a hard-realtime controller without target-specific evidence.

Before such a learned component enters a correctness- or safety-relevant path, the project constitution requires at least:

- a measured limitation of a simpler deterministic/classical baseline;
- exact input, output, and unit contracts;
- supported targets/versions and safe operating envelope;
- uncertainty/defer behavior and fallback;
- training-data provenance and a reproducible manifest;
- held-out evaluation and preregistered thresholds;
- latency, quantization, and hardware measurements;
- artifact identity, rollout, and rollback.

Training is off-device by default; online updates are a separate, later hypothesis. A mini-brain must earn its complexity and can be removed again if the baseline proves equal or better.

## Summary

| Question | Answer today |
| --- | --- |
| Does Engine learn from explicit corrections? | Yes, as a versioned GoalSpec preference |
| Does Engine learn patterns/routines? | Yes, through fixed evidence and shadow gates |
| Does Engine use prior observed success? | Yes, for bounded plan reuse/routing |
| Does Engine learn permissions? | No |
| Does Engine train model weights? | No |
| Does Engine autonomously create mini-brains? | No, roadmap after evidence of need |
| Is fake learning physical effect evidence? | No |

See [All modes](./modes.md) for learning and routine statuses and [The end goal](./end-goal.md) for the role of mini-brains in the longer-term direction.
