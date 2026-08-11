---
title: Multiple plugins and brains
description: How one Heart composes multiple worlds, one executive, and multiple specialists.
sidebar_position: 5
---

# Multiple plugins and brains

Engine can load multiple installed plugins at the same time. Each plugin may
provide multiple targets and specialists. In the current runtime, each
`EngineApplication` has exactly one active executive brain and may have multiple
plugin specialists available.

That distinction matters: "multiple brains" currently means one executive plus
N replaceable specialists, not multiple executive models that vote, negotiate,
or simultaneously possess authority.

## One composed world

The registry sorts plugins and targets by stable ID. At each observation
boundary, the Heart combines the latest target observations into one durable
`WorldSnapshotV2` with:

- an Engine-wide revision;
- an independent revision for each target;
- all entities, relations, and observations;
- coverage, staleness, and provider failures per target.

Goal scope limits which entities an effect may touch and which context is
projected to a brain. The complete connected-world snapshot remains local and
durable so restart and audit do not depend on model context.

Plugins may not share a target ID. Registration fails if two plugins claim the
same target. An entity ID must likewise be stable and canonical; free-form names
or embeddings are not persistence keys.

An autonomy enrollment may project explicitly listed context from another
plugin, but its strategy can propose mutations only through capabilities owned
by its own plugin. Overlapping `(target, entity, conflict_domain)` enrollments
are rejected in the first release. This is context composition, not shared
authority or a cross-plugin workflow engine.

## Current executive selection

Without model configuration, `engine-runtime` composes:

```text
DeterministicExecutiveBrainV2
```

With a configured structured-output model, it composes:

```text
OpenAICompatibleV2Model -> ModelExecutiveBrainV2
```

Both implement the same `ExecutiveBrainV2` protocol and return a
`BrainDecisionV2`. The decision kinds are:

- `query_world`
- `consult_specialist`
- `propose_effect`
- `wait`
- `complete`
- `abandon`

Model output is untrusted data. The Heart binds proposals back to the current
goal and snapshot and validates the family, target, entity, and schema before a
request can be created.

## Multiple specialists

Each plugin may return zero or more `SpecialistBrainV2` objects. The runtime
projects only each specialist's ID and supported capability families to the
executive. If the executive selects `consult_specialist`, the Heart looks up
that exact ID and calls `advise(goal, snapshot, query)`.

The specialist may:

- state whether the request is within its supported scope;
- return a typed `ProposedActionV1`;
- provide a summary and metadata.

It cannot:

- authorize an `ActionRequestV1`;
- bypass policy;
- call an executor directly;
- label an acknowledgement or prediction as an observed effect.

In the current implementation, at most one selected specialist is consulted in
each Heart pass. There is no built-in specialist debate or ensemble loop.

## How selection relates to the Heart

```text
WorldSnapshot + GoalSpec + effect results
  -> bounded context projection
  -> one executive decision
      -> optionally one specialist recommendation
  -> ProposedAction
  -> controller
  -> policy + authorization
  -> executor
  -> fresh observation + oracle
```

The brain selects strategy or a semantic effect. The controller translates that
into exact domain parameters. Policy determines authority. The executor acts.
The oracle uses new observations to determine whether the effect was actually
achieved. None of these roles may silently take over a neighboring role.

## Stable goals are cognitively quiet

When all desired effects are already demonstrably true, an `achieve` goal moves
to `completed` and a `maintain` goal moves to `monitoring` without a brain call.
A successful typed plan can be reused from the plan cache, but only while the
goal version, entity selection, capability manifest, and mandate still match.

Novelty, conflict, unknown evidence, or an observed violation can require the
executive again. An LLM therefore does not occupy a realtime feedback loop.

## Combining plugins without domain leakage

A goal can use facts from different plugins, such as local time from a context
plugin and lighting state from a home plugin. Scoped routine guards give every
leaf its own exact entity selector. The Heart evaluates generic Boolean and time
contracts; the plugin remains responsible for properties, units, capability
families, and device translation.

A plugin may also provide context only or contain only a specialist. Mutating
capability families always require the full provider/controller/executor/oracle
set in the manifest declaration.

## Current limits

- There is no multi-executive orchestrator, voting, fallback chain, or dynamic
  executive routing. Selecting another executive currently means composing a
  different `EngineApplication`.
- There is no marketplace that resolves specialist or plugin versions.
- Plugin processes are not generally sandboxed and artifact signing is not
  enforced.
- `stream` is a contract mode, but it lacks an end-to-end reference proof for
  reconnect and cursor recovery.
- More brains never provide more authority; all proposals pass through the same
  policy and effect path.

If multi-executive behavior affects correctness or safety, it requires an ADR,
tests for deterministic selection and failure isolation, and an explicit answer
to which component produces the one final proposal. A model ensemble must not
become an alternative authorization boundary.
