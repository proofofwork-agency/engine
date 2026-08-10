---
title: Glossary
description: Canonical Engine terms for world state, the action lifecycle, cognition, and learning.
sidebar_position: 3
---

# Glossary

Use these terms precisely. In particular, proposal/authority,
prediction/observation, and state/weights must not be used as synonyms.

## A

### `ACHIEVE`

Goal mode in which a goal becomes `completed` after its fulfilment has been
demonstrated independently. Unlike `MAINTAIN`, the goal does not remain active as
a continuous monitoring loop afterward.

### `ActionRequestV1`

Exact, typed request for one target and entity. It contains the capability,
parameters, snapshot/world/target revision, preconditions, deadline, and an
optional idempotency key. The request is not permission.

### Adapter

Plugin component that translates canonical Engine contracts to a target protocol
and back. The public roles are separated more finely into provider, controller,
executor, and oracle.

### `AuthorizationV1`

Scoped, expiring proof that one exact request type may be executed within a
concrete scope. It binds, among other things, the request hash, target, entity,
capability, limits, snapshot, mandate, and policy decision.

### `AutonomyProfileV1`

Low-risk delegation that the owner has activated explicitly for exact entities,
capability families, routine templates, and limits. In the current first tranche,
this is specific to Homey lighting. The profile is not a general “anything goes”
mode.

## B

### Behavior signal

`BehaviorSignalV1`: plugin evidence about an external change or pattern, with
scope, preference, context, provenance, and evidence grade. Repeated behavior is
not consent.

### Brain

Replaceable deliberative component. The executive chooses a decision kind or
semantic proposal; a specialist advises within capability families. A brain does
not own authoritative world state, policy, authorization, an executor, or a
success oracle.

### Bounded context projection

Temporary, bounded selection of a goal, current relevant world data, effect
results, capabilities, and specialist metadata for a brain. The projection is
not operational state and can be reconstructed.

## C

### Capability

A typed operation offered by a target under explicit input and effect schemas,
units, preconditions, risk/privacy, limits, deadline, invocation mode, and
recovery semantics.

### Capability family

Stable semantic family that groups dynamic target instances. The family is
declared statically; unknown dynamic families remain opaque and read-only.

### Capability graph

Conceptual current collection of targets, capabilities, dependencies, and
availability. The current runtime projects manifests and per-target discovery
into snapshots/context; not every graph operation is exposed as a separate
public CLI command.

### Controller

`DomainController`: translates a semantic proposal into an exact
`ActionRequestV1` within the capability envelope. This is not a realtime device
controller in the sense of a motor or flight-control loop.

### Coverage

Description of the part of the world that an observation or provider output
actually covers. Without complete relevant coverage, absence must not be
interpreted as `false`.

## D

### `DEFER`

Policy outcome: the available evidence is currently insufficient, conflicting,
or unsafe, so policy cannot return allow or a definitive deny.

### Desired effect

Typed desired state within a GoalSpec, bound to a capability family, entity
selector, condition, and semantic parameters.

### Deterministic executive

Provider-free baseline that uses the same untrusted `BrainDecisionV2` seam as a
model executive. This allows known violations to be routed without an LLM.

## E

### Effect oracle

Plugin role that reconciles the proposal, pre-state, receipt, and fresh
post-state. The oracle produces an `EffectDeltaV1`; it must return unknown when
its measurements are insufficient.

### `EffectDeltaV1`

Durable description of observed change between two snapshots, including the
evidence grade, `achieved` as true/false/null, observation IDs, and reason.

### Entity

Stably identified object in a target world, such as a warehouse bin or device
zone. A name or embedding is not a canonical identity.

### Evidence grade

Classification as `OBSERVED`, `DERIVED`, `INFERRED`, `UNKNOWN`, `CONFLICTING`, or
`STALE`. It is separate from confidence and quality.

### Executive brain

The single runtime-wide brain that chooses the next cognitive step type in a
Heart application. Current composition: deterministic or one model-backed
executive.

### Execution receipt

`ExecutionReceiptV2`: an executor fact about
requested/accepted/running/succeeded/partial/failed/cancelled/unknown. A receipt
is not proof that a GoalSpec effect was achieved.

### Experience

Historical actions, outcomes, and behavior evidence. Experience is not the same
layer as current state, model weights, or temporary context.

## G

### GoalSpec

`GoalSpecV2`: declarative desired result with scope, desired effects,
preferences, constraints, budgets, stop conditions, mode, and mandate binding.

## H

### Heart

The local, durable runtime core. The Heart observes, reconstructs state,
evaluates goals and routines, calls brains when needed, validates proposals,
runs through policy/authorization/execution, observes again, and stores audit
data. The Heart is not an LLM or a hard-realtime controller.

## I

### Idempotency key

Key that allows a target or executor to recognize that the same logical request
has been submitted again. This requires honest target semantics; the field alone
does not make a non-idempotent physical action safe.

### Imagined state

Ephemeral counterfactual or predicted state. It may help planning, but it is not
an observation and is not stored as authoritative world state.

### Invocation mode

`immediate`, `task`, or `stream`. Immediate returns directly; task has a durable
handle plus polling/cancellation; stream assumes cursor/reconnect support. The
current end-to-end reference covers task, not stream.

## L

### Learning candidate

Durable proposal to change a namespaced preference after validated behavior
evidence. Candidate, shadow, promotion, and rollback are separate states.

### Learning

In Engine: bounded, auditable state/preference or routine adaptation. In the
current runtime, it is not online training of model weights and cannot expand
authority.

### Lease

SQLite-based exclusive ownership of the active runtime for one Engine store,
with heartbeat and loss detection. It prevents two concurrent executive loops
from operating on the same operational state.

## M

### `MAINTAIN`

Goal mode in which Engine continues to monitor a demonstrably desired state and
may act again after observed drift.

### Mandate

`StandingMandateV1`: scope activated by an authorized actor for plugins, targets,
entities, capabilities, limits, privacy, learning, validity, and manifest
versions. A goal or brain does not create its own mandate.

### Mini-brain

A specialized learned component behind a capability contract. It requires,
among other things, scope, uncertainty/defer behavior, provenance, a baseline,
held-out evaluation, hardware measurements, and rollback. Being neural grants
no special authority.

## O

### Observation

`ObservationV1`: typed evidence with entity, property, value, source, time,
evidence grade, unit, quality, coverage, and optional artifact identity.

### Opaque capability

Dynamically discovered family that was not registered statically. It is
projected as query-only, read-only, and observe-only until a typed manifest
family is installed and enrolled.

## P

### Plugin

Installable `engine.plugin/v2` package with a static manifest and runtime
factory. A plugin owns domain semantics and adapters, not Engine's generic
authority.

### Policy decision

Deterministic `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, or `DEFER` with reasons. Only
policy can cause an authorization to be created on the Heart path.

### Prediction

Predicted change. It remains separate from an independently observed effect.

### Proposed action

`ProposedActionV1`: untrusted candidate for one desired effect, bound to a goal
and snapshot. It has no execution rights.

## R

### Relation

Typed, directed relation between two entities with source, time, and evidence
grade. By contract, a `RelationHypothesisV1` remains `INFERRED`.

### Routine

Durable activation layer above one linked GoalSpec. It contains a scoped guard,
recurrence, cooldown, priority, conflict key, and status; it replaces neither
policy nor the goal.

### Routine compiler

Plugin component that turns declared pattern semantics into inert RoutineSpec
and GoalSpec data. It cannot create an authorization.

## S

### Safe state

Target-specific state to seek after failure. Reaching it must be observed again;
Engine does not assume that rollback or stop succeeded.

### Shadow

Counterfactual evaluation phase without dispatch. A real opportunity exists only
when the guard is true and the desired effect is demonstrably false; absence is
not agreement.

### Specialist brain

Plugin brain with declared supported families. It returns typed advice or a
proposal, but no request authority or effect truth.

### State

Current target-bound facts and beliefs. Operational state is durable, typed, and
reconstructible without a provider conversation.

## T

### Target

One concrete software or physical-system boundary under a stable target ID, such
as one warehouse or home controller.

### Target observation

`TargetObservationV2`: one observation boundary for a target, with monotonic
revision, entities, relations, observations, coverage, availability, and errors.

## W

### Weights

Reusable learned model parameters. They are not current world state, experience,
or authority. The current bounded-learning path does not train weights.
