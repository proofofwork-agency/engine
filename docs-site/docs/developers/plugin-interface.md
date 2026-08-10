---
title: Plugin interface v2
description: The static manifest, runtime protocols, and boundary between world semantics and Engine.
sidebar_position: 2
---

# Plugin interface v2

`engine.plugin/v2` is the public boundary between Engine and a world. A plugin
may observe one or more targets and provide typed capabilities, controllers,
executors, effect oracles, specialists, and experience providers. Engine remains
responsible for the generic lifecycle, policy, authorization, and audit.

A plugin always has two sides:

1. a static `engine-plugin.toml`, readable before import;
2. a Python factory in the `engine.plugins` entry point group that returns an
   object with the `WorldPluginV2` surface.

Import and factory invocation should be inert: do not connect, mutate a target,
or start a background process. Connections begin only in an explicit provider
or executor operation.

## Registration

Declare the distribution entry point in `pyproject.toml`:

```toml
[project.entry-points."engine.plugins"]
my_world = "my_world.plugin:load_plugin"
```

The runtime locates the associated `engine-plugin.toml`, validates it, and
compares the static manifest with `plugin.manifest`. A mismatch in identity,
roles, capabilities, preferences, or routines blocks registration. Duplicate
plugin and target IDs are also rejected.

Engine does not currently have a marketplace. Installation and distribution
choices use normal Python packaging and remain under local operator control.

## Minimal manifest

A mutating capability needs more information than a tool name:

```toml
[plugin]
id = "example.warehouse"
version = "0.1.0"
engine_api = ">=2.0,<3"
contract_version = "engine.plugin/v2"
description = "Bounded warehouse world"

[declarations]
world_providers = ["warehouse"]
controllers = ["warehouse-controller"]
executors = ["warehouse-executor"]
effect_oracles = ["warehouse-oracle"]
specialists = []
entity_types = ["warehouse.bin"]
relation_types = []
observation_types = ["bin.count"]
experience_providers = []
routine_compilers = []

[needs]
network = []
filesystem = []
secrets = []
privacy = []

[store]
identity = "example.warehouse.store"
schema_version = 1

[[capability_families]]
id = "example.warehouse.transfer-bin/v1"
family = "warehouse.transfer-bin"
version = "1.0.0"
description = "Move a bounded number of crates"
control_layer = "semantic"
invocation_mode = "task"
risk_class = "low"
privacy_class = "local"
idempotent = true
deadline_ms = 5000
input_schema = {type = "object", required = ["from", "to", "count"]}
effect_schema = {type = "object", required = ["minimum_count"]}
effect_measurements = ["bin.count"]
limits = {count = {min = 1, max = 10}}
recovery = "poll_task_then_observe"
```

The manifest declares needs; it does not enforce those needs by itself. The
current runtime does not yet provide general sandbox or permission enforcement
based on `[needs]`, and it does not cryptographically verify plugin artifacts.
Treat signing and sandboxing as open product gaps, not existing safety guarantees.

## Roles

### `WorldProvider`

A provider owns a `plugin_id`, a stable `target_id`, polling and freshness
intervals, and implements:

- `discover()` for capability instances;
- `observe()` for a monotonic `TargetObservationV2`;
- `subscribe(wake)` as an optional wake-up source.

`observe()` returns entities, relations, observations, coverage, source, target
revision, and availability. An event is only a reason to observe again; the event
itself is not automatically operational truth.

### `DomainController`

The controller translates a semantic `ProposedActionV1` into an exact
`ActionRequestV1`. This is where domain meaning, units, target parameters,
target revision, deadline, and idempotency key are fixed. The controller may not
change the target, entity, goal, or capability.

### `Executor`

The executor receives only a concrete request plus an `AuthorizationV1`. It
implements `dispatch`, `poll`, and `cancel`, and returns an
`ExecutionReceiptV2`. A receipt states what the executor knows about execution;
an acknowledgement does not prove that the intended effect exists in the world.

### `EffectOracle`

The oracle compares the proposal, pre-snapshot, receipt, and a fresh
post-snapshot. It produces an `EffectDeltaV1` with evidence grade,
`achieved: true | false | null`, measurements, and a reason. With insufficient
coverage, `null`/`UNKNOWN` is more accurate than `false`.

### `SpecialistBrainV2`

A specialist declares supported capability families and returns typed
`SpecialistAdviceV1`. It may provide a proposal, but cannot authorize, dispatch,
or establish its own success.

### `ExperienceProvider`

An experience provider publishes cursor-based `BehaviorBatchV1` values from
plugin-owned storage. Engine stores signals exactly once per cursor and may link
them to a namespaced preference or routine template. A behavior signal is
evidence, not implicit permission.

### `RoutineCompiler`

A routine compiler translates plugin-owned pattern semantics into an inert
`RoutineSpecV1` plus `GoalSpecV2`. It cannot create a mandate or authorization.

## Discovery is bounded by the manifest

A provider may discover dynamic devices, but only previously declared capability
families can enter the mutating path. An unknown family is projected as
`opaque`, `query`, `read_only`, and `observe_only`. A newly discovered target
device therefore cannot create new authority automatically.

For mutating capabilities, the manifest validator requires at least a provider,
controller, executor, and effect oracle. A v1 plugin may remain visible through
the compatibility bridge, but is observe-only in the v2 world runtime.

## Mutation lifecycle

```text
fresh observation
  -> untrusted proposal
  -> scope and schema validation
  -> controller creates exact request
  -> deterministic policy
  -> request-bound authorization
  -> executor dispatch/poll/cancel
  -> fresh post-observation
  -> plugin oracle reconciles effect
  -> receipt and EffectDelta are stored durably
```

A capability with `immediate` can respond terminally at once. `task` uses a
durable external handle, polling, deadline cancellation, and restart recovery.
`stream` exists in the public contract and the store has scaffolding, but there
is no end-to-end stream reference proving reconnect and cursor recovery yet.

## Storage boundary

A plugin declares its own store identity and schema version. Plugin data does not
belong in Engine's private operational tables, and Engine does not share a
mutable database as an implicit interface. Exchange public contract values only.

## What conformance does and does not prove

`engine-plugin validate` validates the static manifest. `engine-plugin test`
runs the generated `unittest` suite. `engine_sdk.check_plugin()` checks identities,
duplicate targets, provider observations, declarations, and undeclared families,
among other structural properties.

That proves contract shape and fake behavior. It does not prove network
isolation, artifact signing, a physical safe state, timing guarantees, or
certification.

