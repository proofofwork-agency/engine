---
title: Architecture
sidebar_position: 3
description: The canonical Engine v2 architecture, plugin roles, stores, and complete action lifecycle.
---

# Architecture

The canonical product route is `engine.plugin/v2`: dependency-light contracts in `engine-sdk`, the generic Heart and store in `src/engine`, and composition, discovery, and CLI in `engine-runtime`. The older v1 core remains available as compatibility evidence, but v1 plugins are observe-only in the v2 world.

> **Status:** the v2 vertical software slice is **Implemented** and **Fake/simulation-tested** with Homey and a reference warehouse. Whole-world Homey observation is **Live read-only**; live v2 mutation and physical certification are **Roadmap**.

## Layers

```text
Intent surfaces (human, CLI, later other clients)
        |
        v
GoalSpecV2 + StandingMandateV1       durable Engine state
        |
        v
WorldHeartV2 ----------------------> WorldStore (SQLite/WAL)
   |         |          |
   |         |          +----------> general brain + specialists
   |         +---------------------> policy + authorization
   +-------------------------------> PluginRegistryV2
                                         |
                 +-----------------------+----------------------+
                 |          |            |          |           |
          WorldProvider  Controller   Executor   Oracle   Experience/Routine
                 |          |            |          |           |
                 +---------------------- target/world -----------+
```

The Heart is generic. The plugin owns the meaning of “light,” “crate,” “file,” or “robot pose.” A target may have its own store, but it does not share mutable operational tables with Engine.

## Durable objects

| Object | Role |
| --- | --- |
| `WorldSnapshotV2` | An immutable logical observation boundary composed from target observations with independent monotonic revisions |
| `ObservationV1` | Typed evidence with source, time, grade, unit, quality, coverage, and optional artifact identity |
| `GoalSpecV2` | Desired effect, scope, constraints, budgets, stop conditions, preferences, mode, and version |
| `CapabilitySpecV2` | Static capability contract: schemas, control layer, invocation mode, risk, privacy, deadline, units, limits, and recovery |
| `ProposedActionV1` | Untrusted semantic proposal bound to a goal, effect, entity, and snapshot |
| `ActionRequestV1` | Exact request with capability, parameters, preconditions, revisions, deadline, and idempotency key |
| `PolicyDecisionV1` | `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, or `DEFER`, including reasons and policy version |
| `AuthorizationV1` | Temporary proof bound to request hash, target, entity, capability, limits, snapshot, and expiry |
| `ExecutionReceiptV2` | What the executor actually accepted, executed, or could not determine |
| `EffectDeltaV1` | Difference between pre- and post-state, with evidence grade and `achieved: true/false/unknown` |

A model transcript is none of these objects and cannot replace them.

## The complete v2 lifecycle

A mutating pass proceeds as follows.

### 1. Observe a logical world boundary

Each `WorldProvider` supplies entities, relations, and observations for its target. The Heart composes them into a `WorldSnapshotV2`. Provider failures, staleness, and missing coverage remain visible. An event is only a wake hint; its payload does not automatically become canonical state.

### 2. Evaluate routine, stop conditions, and desired effects

If a linked routine exists, Engine first checks authority, guard, recurrence, cooldown, conflict, and action limits. It then evaluates the declarative goal conditions against the snapshot.

- Everything true + `ACHIEVE` -> `completed`.
- Everything true + `MAINTAIN` -> `monitoring`, without a brain call.
- Required evidence unknown -> `uncertain`, without mutation.
- Stop condition true -> `abandoned`.
- An observed violation -> cognition may start.

### 3. Reuse a valid plan or project bounded context

A previously successful typed plan may be reused only when the deterministic situation key, goal version, capability manifest fingerprint, and mandate still match. Otherwise, `BoundedContextProjector` builds a target- and goal-focused subset containing entities, one-hop relations, observations, effect results, capabilities, and specialists. The complete world remains local and durable.

### 4. Let the general brain return an untrusted decision

The executive brain selects one of the cognitive decision kinds. It may provide a `ProposedActionV1` directly or select a specialist. A specialist returns `SpecialistAdviceV1` and optionally a typed proposal. Every brain call receives a snapshot binding, projection hash, output record, goal/purpose, and latency record.

### 5. Validate the proposal

The Heart checks, among other things:

- the same goal and desired effect;
- the same current snapshot and world revision;
- the capability family has not changed;
- entity and target fall within the effect selector;
- the capability is statically known and not `opaque`/observe-only;
- semantic parameters satisfy the effect schema.

A rejected proposal remains auditable and receives no execution rights.

### 6. Concretize and validate the exact request

A plugin `DomainController` translates the semantic effect into an `ActionRequestV1`. The Heart verifies identities, target revision, input schema, and every capability/request precondition. The controller may not select another target, entity, or capability.

This is the boundary between strategy and device meaning: a brain selects “achieve this effect”; the controller determines the exact protocol request within the capability envelope.

### 7. Evaluate policy and create authorization

The deny-by-default policy compares the request with the `StandingMandateV1`, current plugin manifest version, privacy, risk class, and parameter limits. Only `ALLOW` can produce an `AuthorizationV1`. Authorization binds cryptographically to the request hash and expires no later than the request or mandate expiry.

`DENY`, `DEFER`, and `REQUIRE_APPROVAL` stop before dispatch. No brain, controller, or plugin executor can create this proof itself.

### 8. Dispatch and record the receipt

The `Executor` receives the exact request and authorization. A valid `ExecutionReceiptV2` must carry matching identities. Adapter exceptions or contradictory receipts are recorded as terminal `UNKNOWN`; the lifecycle does not remain silently stuck at `REQUESTED`.

### 9. Observe again

After dispatch, the Heart creates a fresh world snapshot. An HTTP acknowledgement, returned text, or model confidence is not post-state.

### 10. Reconcile with the effect oracle

The plugin `EffectOracle` compares proposal, pre-snapshot, receipt, and post-snapshot. The result is an `EffectDeltaV1` with measured changes, observation IDs, evidence grade, and an independent `achieved` judgment. A broken oracle yields `UNKNOWN`, never silent success.

### 11. Update goal status, wakes, cache, and audit state

Engine evaluates the goal again:

- effect reached -> `completed` or `monitoring`;
- evidence unknown -> `uncertain`;
- task still `accepted/running` -> `waiting` plus a durable poll wake;
- otherwise -> `active` for another pass.

All lifecycle objects remain stored. Only an observed successful, exactly bound route can feed the deterministic plan cache.

## `TASK` variation

A task executor may return `ACCEPTED` or `RUNNING` with an `external_handle`. The Heart stores the nonterminal lifecycle and schedules a durable wake. On the next pass it:

1. loads the proposal, request, authorization, and latest receipt;
2. polls the handle, or cancels it when the deadline is reached;
3. records the new receipt;
4. observes again;
5. reconciles through the same oracle;
6. schedules another wake while the task remains nonterminal.

This route is **Implemented** and **Fake/simulation-tested** in the reference warehouse, including process restart and deadline cancellation. `STREAM` exists in the contracts but does not yet have a comparable end-to-end reference proof.

## Plugin interface

Every v2 plugin has an inert static `engine-plugin.toml` and a Python entry point in the `engine.plugins` group. The runtime reads the static manifest first and compares it with the loaded plugin. Factory construction should not open a network connection or mutate a target.

The public roles are deliberately separated:

| Role | May | May not |
| --- | --- | --- |
| `WorldProvider` | Discover capabilities, observe, optionally subscribe wake hints | Choose goals or mutate a target |
| `DomainController` | Concretize a semantic proposal within the capability contract | Create authority or confirm an effect |
| `Executor` | Dispatch an authorized request, poll/cancel tasks | Choose strategy |
| `EffectOracle` | Reconcile pre-state, receipt, and post-state | Present a prediction as observation |
| `SpecialistBrainV2` | Provide bounded advice/a typed proposal | Execute or authorize |
| `ExperienceProvider` | Publish cursor-based behavior signals | Patch GoalSpecs or infer permission |
| `RoutineCompiler` | Translate a plugin pattern into inert routine/goal data | Create a mandate |

A plugin may use only mutable capability families declared statically and enrolled. Unknown dynamic capabilities are projected as `opaque`, `QUERY`, and read-only.

## SDK and runtime

### `engine-sdk` — **Implemented**

Contains public data types, protocols, manifest validation, conformance helpers, and `engine-plugin` scaffolding. The `world`, `specialist`, and `full` templates generate a separately installable plugin structure. Plugin authors do not need to import the complete Heart runtime.

### `engine-runtime` — **Implemented**

Contains entry-point discovery, composition, runtime lease, signal handling, model configuration, and the `engine` CLI. Important surfaces cover plugin inspection, world observation, setup preview/activation, run/status, learning, routines, bounded YOLO enrollment, and model canary.

### Maturity boundary

The interfaces and reference plugin form a coherent alpha. They are not yet evidence of a large third-party ecosystem, cross-language SDK, production supervisor, or universal target support.

## Stores and isolation

Engine uses its own SQLite/WAL ledger for world snapshots, goals, lifecycle objects, brain calls, wakes, evidence, candidates, and routines. A plugin may use its own versioned store for target identities or raw domain evidence. Store identities remain separate; a plugin does not write directly to Engine tables.

This makes reconstruction possible without model memory and prevents a plugin from silently becoming authoritative Engine state.

## Realtime and safety boundary

```text
Engine Heart: intent, observation, deliberation, policy, audit
        |
        | high-level, bounded, authorized request
        v
Target controller: protocol, timing, local limits, watchdogs
        |
        v
Independent safety/interlocks and physical system
```

A target controller may further restrict or refuse request parameters. Engine policy never replaces the physical safety plane. Read [What Engine is not](./what-engine-is-not.md) and [All modes](./modes.md) for the related statuses and risk classes.
