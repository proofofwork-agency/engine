---
title: Frequently asked questions
description: Short answers about the Heart, brains, plugins, learning, safety, and current limits.
sidebar_position: 4
---

# Frequently asked questions

## Is Engine an AI agent?

Not primarily. Engine is a local runtime for living goals, typed world state,
and an auditable action lifecycle. An LLM or agent can provide an executive brain
or intent compiler, but remains a proposal provider. Policy, authorization,
execution, and effect truth remain outside the model.

## What is the difference between the Heart and a brain?

The Heart owns the durable loop and operational state. It observes, evaluates,
validates, asks policy, records authorizations and receipts, and observes again.
A brain chooses a typed next step or semantic proposal when novelty or drift
requires deliberation. A brain can be replaced or become unavailable without
losing world state.

## Does Engine work without an LLM?

Yes, for the core runtime, observation, deterministic executive, typed goals,
plugins, policy, execution, oracle, and tests. The current `engine setup` path
for free-form natural language does require a configured structured-output
model. An application can also create a typed GoalSpec itself.

## Can I use multiple models at the same time?

You can have multiple plugin specialists. Each current `EngineApplication` has
exactly one active executive: deterministic or one OpenAI-compatible model
adapter. Multi-executive voting, fallback, or ensemble routing is not yet
implemented.

Additional brains would receive no additional authority: every proposal must
pass through the same validation, policy, authorization, and oracle.

## Can one goal use multiple plugins?

Yes. The Heart composes all connected target observations into one snapshot,
and a GoalSpec may use entities and conditions across multiple targets. Scoped
routine guards can, for example, combine a time entity from a context plugin
with a device zone from another plugin. Mutating desired effects remain bound to
an exact capability family, target, and entity.

## Is every Python plugin trusted automatically?

No. Engine compares the static and loaded manifests and keeps unknown families
observe-only, but the current runtime has no general process sandbox and does
not enforce manifest needs at the OS or network level. Plugin artifact signing
is not enforced either. Install only code that you trust at the deployment
level.

## Is there a plugin marketplace?

No. Discovery uses locally installed Python distributions with the
`engine.plugins` entry-point group. There is not yet a marketplace, automatic
trust chain, or version-resolver service.

## Can a plugin give itself new capabilities?

Not for mutation. Dynamic discovery may expose new instances, but a family that
was not declared in advance in `engine-plugin.toml` becomes opaque, query-only,
and read-only. A static manifest plus enrollment/mandate is required before
authority can exist.

## Which modes exist?

At the goal level, there are `achieve` and `maintain`. At the capability level,
there are `immediate`, `task`, and `stream`. Cognitive decisions use
`query_world`, `consult_specialist`, `propose_effect`, `wait`, `complete`, and
`abandon`. There is also a bounded `yolo` autonomy profile for the first Homey
lighting tranche; it is not an unrestricted mode.

## Are `task` and `stream` production-ready?

`task` has a non-home reference proof with a durable handle, polling, deadline
cancellation, and reconstruction after restart. `stream` exists in the contract
and store scaffolding, but lacks an end-to-end reference proof for reconnect and
cursor recovery. Each concrete target must also be assessed independently.

## What does “Engine learns” mean?

The current learning path imports plugin-owned behavior evidence, validates its
scope and schema, creates a candidate, runs at least a bounded shadow phase, and
may then store a new GoalSpec preference or routine version. Promotion is
auditable and reversible and must never expand target, capability, risk,
privacy, or authority.

This is not online training of model weights. Engine can therefore adjust a
preference or state without retraining a model.

## Can Engine write or improve skills itself?

Not as part of the current product core. A plugin or external system can propose
new code or a skill, but installation, trust, signing, sandboxing, tests, and
enrollment remain separate steps. Self-modifying code does not gain authority
automatically.

## Is an execution receipt the same as success?

No. A receipt reports what the executor says about execution. A fresh world
observation must then follow, and the plugin oracle must reconcile the desired
effect against relevant measurements. An ACK without an effect can therefore
produce a `succeeded` receipt while still yielding `achieved = false` or `null`.

## Why is missing telemetry not simply `false`?

Absence proves a negative fact only when the source guarantees complete relevant
coverage. An offline sensor, incomplete query, or stale snapshot does not say
that a door is closed, a lamp is off, or a relation is absent. Engine records
`UNKNOWN` or `STALE` and fails closed for mutation.

## Does policy replace an emergency stop or hardware interlock?

No. Software policy constrains requests but does not replace an emergency stop,
watchdog, force/temperature limiter, certified PLC, or realtime controller. A
model cannot overrule that independent safety plane either.

## Can Engine control motors, drones, or cars directly?

Not in a hard-realtime loop. Realtime stabilization and actuator feedback
belong in a validated local controller. Engine can propose and authorize a
bounded task at a higher semantic level when a suitable adapter, safety
boundary, and independent observation/oracle exist.

## Does Engine replace Home Assistant, ROS 2, MCP, or an agent framework?

No. Those systems occupy different or overlapping layers and can work with
Engine. Home Assistant or openHAB can provide home worlds, ROS 2 can provide a
robotics body/controller layer, MCP can transport context and tools, and an
agent framework can provide intent/deliberation. Engine's own focus is typed
operational state plus the proposal/authority/effect separation.

## Can I install Engine from PyPI now?

This documentation makes no PyPI installation claim. Use the repository
workspace:

```console
uv sync --all-packages --locked
```

Then run commands with `uv run`.

## Where is the local database?

By default, it is `.engine/engine.sqlite3`, relative to the working directory.
Set `ENGINE_DATABASE` to another explicit path. Plugin-owned stores have their
own identity and migration version and must not leak into this database
interface as shared private tables.

## What happens when two runtimes use the same store?

The operational CLI uses an exclusive SQLite lease with a heartbeat. A second
active owner is rejected; loss of the lease requires the running Heart to stop.
This protects against two executives mutating the same store concurrently, but
it is not a distributed consensus protocol for multiple hosts.

## What is Engine's end goal?

The thesis is a local-first runtime that can turn human intent into typed,
bounded, and auditable actions across heterogeneous software and physical
systems, while models remain optional proposal providers, realtime controllers
retain their authority, and an independent policy/safety boundary constrains
execution. That policy boundary does not itself make a physical system safe.

The next increment of value comes from supporting or falsifying that thesis in
small, measurable worlds. The end goal is not a demo that merely looks
autonomous, a universal butler, or a certification claim without external
evidence.

## What major gaps remain?

- no marketplace;
- no enforced plugin signing;
- no general sandbox or needs enforcement;
- no end-to-end stream reference;
- no multi-executive runtime;
- no universal physical-safety or certification claim.

These gaps remain visible deliberately so the documentation does not present a
roadmap item as an implemented capability.
